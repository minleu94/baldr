from __future__ import annotations

import warnings
from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest

from app_module.recommendation_dataframe_provider import RecommendationDataFrameProvider


class _FixedScore:
    def __init__(self) -> None:
        self.inputs: list[pd.DataFrame] = []

    def generate_recommendations(self, stock_data: pd.DataFrame, config: dict) -> pd.DataFrame:
        self.inputs.append(stock_data.copy(deep=True))
        result = stock_data.copy(deep=True)
        result["FinalScore"] = 80
        return result


class _FixedReasonEngine:
    def generate_reasons(self, latest_row: pd.Series, config: dict) -> list[str]:
        return ["dtype-oracle"]

    def format_reason_text(self, reasons: list[str], max_reasons: int = 3) -> str:
        return "|".join(reasons[:max_reasons])


def _provider_and_scorer() -> tuple[RecommendationDataFrameProvider, _FixedScore]:
    provider = RecommendationDataFrameProvider()
    scorer = _FixedScore()
    provider.strategy_configurator = scorer
    provider.reason_engine = _FixedReasonEngine()
    return provider, scorer


def _history(
    dtype: str,
    *,
    closes: list[int | float] | None = None,
    volumes: list[int | float] | None = None,
) -> pd.DataFrame:
    size = len(closes) if closes is not None else len(volumes) if volumes is not None else 21
    dates = pd.date_range("2026-08-01", periods=size, freq="D")
    close_values = closes if closes is not None else [100] * (size - 1) + [101]
    volume_values = volumes if volumes is not None else [100] * size
    return pd.DataFrame(
        {
            "日期": [int(value.strftime("%Y%m%d")) for value in dates],
            "證券代號": ["DTYPE"] * size,
            "證券名稱": ["dtype fixture"] * size,
            "收盤價": np.asarray(close_values, dtype=dtype),
            "成交股數": np.asarray(volume_values, dtype=dtype),
        }
    )


def _legacy_price_change(history: pd.DataFrame) -> object:
    close_col = "收盤價"
    previous = pd.to_numeric(history.iloc[-2].get(close_col, 0), errors="coerce")
    current = pd.to_numeric(history.iloc[-1].get(close_col, 0), errors="coerce")
    return ((current - previous) / previous * 100) if previous and not pd.isna(previous) else 0


def _terminal(operation: Callable[[], object]) -> tuple[object, ...]:
    try:
        return ("value", operation())
    except Exception as exc:
        return ("exception", type(exc), str(exc))


@pytest.mark.parametrize(
    ("dtype", "threshold"),
    [
        ("float16", "1.0001"),
        ("float32", "1.0001"),
        ("float32", "1.0000001"),
        ("float32", "1.00000001"),
        ("float64", "1.00000001"),
        ("float64", "1.0000001"),
    ],
)
def test_legacy_price_change_min_preserves_numpy_dtype_comparison(
    dtype: str,
    threshold: str,
) -> None:
    history = _history(dtype, closes=[100] * 19 + [100, 101])
    assert history["收盤價"].dtype == np.dtype(dtype)
    provider, scorer = _provider_and_scorer()
    # 每個 runtime 以舊 NumPy scalar `<` 作 oracle，不固定 NumPy 1/2 間的結果。
    expected_accept = not bool(_legacy_price_change(history) < float(threshold))

    result = provider(history, {"filters": {"price_change_min": threshold}}, top_n=5)

    assert ([item["stock_code"] for item in result] == ["DTYPE"]) is expected_accept
    assert (len(scorer.inputs) == 1) is expected_accept
    if expected_accept:
        assert scorer.inputs[0]["收盤價"].dtype == np.dtype(dtype)


@pytest.mark.parametrize(
    "dtype",
    ["float16", "float32", "float64"],
)
def test_legacy_price_change_max_preserves_numpy_dtype_comparison(
    dtype: str,
) -> None:
    history = _history(dtype, closes=[100] * 19 + [100, 101])
    provider, scorer = _provider_and_scorer()
    expected_accept = not bool(_legacy_price_change(history) > float("0.9999"))

    result = provider(history, {"filters": {"price_change_max": "0.9999"}}, top_n=5)

    assert ([item["stock_code"] for item in result] == ["DTYPE"]) is expected_accept
    assert (len(scorer.inputs) == 1) is expected_accept


def test_large_price_max_matches_each_runtime_native_price_scalar() -> None:
    history = _history("float16", closes=[0.01] * 19 + [0.01, 65])
    with np.errstate(over="ignore"):
        legacy_price_change = _legacy_price_change(history)
        expected_accept = not bool(legacy_price_change > float("1e100"))

    provider, scorer = _provider_and_scorer()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        result = provider(
            history,
            {"filters": {"price_change_max": "1e100"}},
            top_n=5,
        )

    assert ([item["stock_code"] for item in result] == ["DTYPE"]) is expected_accept
    assert (len(scorer.inputs) == 1) is expected_accept


@pytest.mark.parametrize(
    "dtype",
    ["float16", "float32", "float64"],
)
def test_legacy_volume_ratio_threshold_comparison_preserves_numpy_dtype(
    dtype: str,
) -> None:
    history = _history(dtype, volumes=[100] * 20 + [101])
    assert history["成交股數"].dtype == np.dtype(dtype)
    provider, scorer = _provider_and_scorer()
    average_volume = pd.to_numeric(history["成交股數"].iloc[-21:-1], errors="coerce").mean()
    latest_volume = pd.to_numeric(history["成交股數"].iloc[-1], errors="coerce")
    volume_change = ((latest_volume / average_volume) - 1) * 100 if average_volume else 0
    raw_threshold = float("1.01")
    effective_threshold = (raw_threshold - 1) * 100 if -50 <= raw_threshold <= 10 else raw_threshold
    expected_accept = not bool(volume_change < effective_threshold)

    result = provider(history, {"filters": {"volume_ratio_min": "1.01"}}, top_n=5)

    assert ([item["stock_code"] for item in result] == ["DTYPE"]) is expected_accept
    assert (len(scorer.inputs) == 1) is expected_accept
    if expected_accept:
        assert scorer.inputs[0]["成交股數"].dtype == np.dtype(dtype)


@pytest.mark.parametrize(
    ("dtype", "raw_ratio_threshold"),
    [
        ("float16", "1.09964"),
        ("float32", "1.1000000191734864"),
        ("float64", "1.1000000191734864"),
    ],
)
def test_legacy_volume_weak_cast_keeps_dtype_specific_ratio_boundary(
    dtype: str,
    raw_ratio_threshold: str,
) -> None:
    history = _history(dtype, volumes=[100] * 20 + [110])
    provider, scorer = _provider_and_scorer()
    effective_threshold = provider._normalize_volume_threshold(float(raw_ratio_threshold))
    volume_ma20 = history["成交股數"].iloc[-21:-1].mean()
    latest_volume = history["成交股數"].iloc[-1]
    legacy_metric = ((latest_volume / volume_ma20) - 1) * 100
    expected_accept = not bool(legacy_metric < effective_threshold)

    result = provider(
        history,
        {"filters": {"volume_ratio_min": raw_ratio_threshold}},
        top_n=5,
    )

    assert ([item["stock_code"] for item in result] == ["DTYPE"]) is expected_accept
    assert (len(scorer.inputs) == 1) is expected_accept


def test_float16_price_change_is_safe_but_large_max_comparison_overflows_in_raise_mode() -> None:
    history = _history("float16", closes=[100] * 20 + [101])
    provider, scorer = _provider_and_scorer()

    with np.errstate(over="raise"):
        legacy_terminal = _terminal(
            lambda: not bool(_legacy_price_change(history) > float("1e100"))
        )
        provider_terminal = _terminal(
            lambda: bool(
                provider(
                    history,
                    {"filters": {"price_change_max": "1e100"}},
                    top_n=5,
                )
            )
        )

    assert provider_terminal == legacy_terminal
    assert (len(scorer.inputs) == 1) is (
        legacy_terminal == ("value", True)
    )


def test_invalid_price_max_string_raises_value_error_before_scorer() -> None:
    history = _history("float16", closes=[100] * 20 + [101])
    provider, scorer = _provider_and_scorer()

    with np.errstate(over="raise"):
        with pytest.raises(ValueError, match="could not convert string to float"):
            provider(
                history,
                {"filters": {"price_change_max": "bad"}},
                top_n=5,
            )

    assert scorer.inputs == []


@pytest.mark.parametrize("price_max", ["1e100", "bad"])
def test_rejected_price_min_short_circuits_price_max_conversion(price_max: str) -> None:
    history = _history("float16", closes=[100] * 20 + [101])
    provider, scorer = _provider_and_scorer()

    with np.errstate(over="raise"):
        result = provider(
            history,
            {"filters": {"price_change_min": "100", "price_change_max": price_max}},
            top_n=5,
        )

    assert result == []
    assert scorer.inputs == []
