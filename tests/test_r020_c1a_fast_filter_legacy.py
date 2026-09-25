from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app_module.recommendation_dataframe_provider import RecommendationDataFrameProvider
from app_module.recommendation_replay_service import RecommendationReplayService


class _RecordingScorer:
    def __init__(self, *, fail_codes: set[str] | None = None) -> None:
        self.inputs: list[pd.DataFrame] = []
        self.fail_codes = fail_codes or set()

    def generate_recommendations(self, stock_data: pd.DataFrame, config: dict) -> pd.DataFrame:
        self.inputs.append(stock_data.copy(deep=True))
        stock_code = str(stock_data["證券代號"].iloc[0])
        if stock_code in self.fail_codes:
            raise RuntimeError(f"synthetic scorer failure: {stock_code}")
        result = stock_data.copy(deep=True)
        result["FinalScore"] = 80
        return result


class _FixedReasonEngine:
    def generate_reasons(self, latest_row: pd.Series, config: dict) -> list[str]:
        return ["synthetic"]

    def format_reason_text(self, reasons: list[str], max_reasons: int = 3) -> str:
        return "|".join(reasons[:max_reasons])


class _RecordingProvider:
    def __init__(self, provider: RecommendationDataFrameProvider) -> None:
        self.provider = provider
        self.inputs: list[pd.DataFrame] = []

    def __call__(self, data: pd.DataFrame, config: dict, top_n: int) -> list[dict]:
        self.inputs.append(data.copy(deep=True))
        return self.provider(data, config, top_n)


class _FloatProbe:
    def __init__(
        self,
        name: str,
        calls: list[str],
        *,
        value: float | None = None,
        fail: bool = False,
    ) -> None:
        self.name = name
        self.calls = calls
        self.value = value
        self.fail = fail

    def __float__(self) -> float:
        self.calls.append(self.name)
        if self.fail or self.value is None:
            raise ValueError(f"synthetic invalid filter value: {self.name}")
        return self.value


def _configured_provider(
    scorer: _RecordingScorer | None = None,
) -> tuple[RecommendationDataFrameProvider, _RecordingScorer]:
    actual_scorer = scorer or _RecordingScorer()
    provider = RecommendationDataFrameProvider()
    provider.strategy_configurator = actual_scorer
    provider.reason_engine = _FixedReasonEngine()
    return provider, actual_scorer


def _history(
    stock_code: str,
    *,
    closes: list[float] | None = None,
    volumes: list[float] | None = None,
    available_dates: list[object] | None = None,
) -> pd.DataFrame:
    size = len(closes) if closes is not None else len(volumes) if volumes is not None else 21
    dates = pd.date_range("2026-08-12", periods=size, freq="D")
    actual_closes = closes if closes is not None else [100.0] * size
    actual_volumes = volumes if volumes is not None else [100.0] * size
    rows: list[dict[str, object]] = []
    for index, current_date in enumerate(dates):
        row: dict[str, object] = {
            "日期": int(current_date.strftime("%Y%m%d")),
            "證券代號": stock_code,
            "證券名稱": f"name-{stock_code}",
            "收盤價": actual_closes[index],
            "成交股數": actual_volumes[index],
        }
        if available_dates is not None:
            row["available_date"] = available_dates[index]
        rows.append(row)
    return pd.DataFrame(rows)


def _codes(frames: list[pd.DataFrame]) -> list[str]:
    return [str(frame["證券代號"].iloc[0]) for frame in frames]


def test_nan_price_and_volume_numerators_pass_enabled_legacy_thresholds() -> None:
    price_provider, price_scorer = _configured_provider()
    price_result = price_provider(
        _history("PRICE-NAN", closes=[100.0] * 19 + [np.nan]),
        {"filters": {"price_change_min": "5"}},
        top_n=5,
    )

    volume_provider, volume_scorer = _configured_provider()
    volume_result = volume_provider(
        _history("VOLUME-NAN", volumes=[100.0] * 20 + [np.nan]),
        {"filters": {"volume_ratio_min": "1.5"}},
        top_n=5,
    )

    assert [item["stock_code"] for item in price_result] == ["PRICE-NAN"]
    assert _codes(price_scorer.inputs) == ["PRICE-NAN"]
    assert [item["stock_code"] for item in volume_result] == ["VOLUME-NAN"]
    assert _codes(volume_scorer.inputs) == ["VOLUME-NAN"]


def test_zero_and_nan_denominators_fall_back_to_zero_then_still_apply_threshold() -> None:
    price_history = pd.concat(
        [
            _history("PRICE-ZERO-DENOM", closes=[100.0] * 18 + [0.0, 100.0]),
            _history("PRICE-NAN-DENOM", closes=[100.0] * 18 + [np.nan, 100.0]),
        ],
        ignore_index=True,
    )
    price_provider, price_scorer = _configured_provider()
    price_result = price_provider(
        price_history,
        {"filters": {"price_change_min": "1"}},
        top_n=10,
    )

    volume_history = pd.concat(
        [
            _history("VOLUME-ZERO-DENOM", volumes=[0.0] * 20 + [100.0]),
            _history("VOLUME-NAN-DENOM", volumes=[np.nan] * 20 + [100.0]),
        ],
        ignore_index=True,
    )
    volume_provider, volume_scorer = _configured_provider()
    volume_result = volume_provider(
        volume_history,
        {"filters": {"volume_ratio_min": "1.5"}},
        top_n=10,
    )

    assert price_result == []
    assert price_scorer.inputs == []
    assert volume_result == []
    assert volume_scorer.inputs == []


def test_price_float_comparison_rejects_1000_to_1101_at_max_10_1() -> None:
    price_change = ((1101.0 - 1000.0) / 1000.0) * 100
    assert price_change == 10.100000000000001

    provider, scorer = _configured_provider()
    result = provider(
        _history("PRICE-EDGE", closes=[1000.0] * 19 + [1101.0]),
        {"filters": {"price_change_max": "10.1"}},
        top_n=5,
    )

    assert result == []
    assert scorer.inputs == []


def test_volume_ratio_1_1_float_normalization_matches_20_by_100_latest_110_boundary() -> None:
    metric = ((110.0 / 100.0) - 1) * 100
    provider, scorer = _configured_provider()

    assert metric == 10.000000000000009
    assert provider._normalize_volume_threshold(float("1.1")) == 10.000000000000009
    result = provider(
        _history("VOLUME-EDGE", volumes=[100.0] * 20 + [110.0]),
        {"filters": {"volume_ratio_min": "1.1"}},
        top_n=5,
    )

    assert [item["stock_code"] for item in result] == ["VOLUME-EDGE"]
    assert _codes(scorer.inputs) == ["VOLUME-EDGE"]


@pytest.mark.parametrize(
    ("raw_threshold", "latest_volume", "expected_normalized_threshold", "expected_codes"),
    [
        ("10.0000000000000001", 110.0, 900.0, []),
        ("-50.000000000000001", 0.0, -5100.0, ["CONFIG-EDGE"]),
    ],
)
def test_volume_threshold_uses_legacy_float_before_normalization(
    raw_threshold: str,
    latest_volume: float,
    expected_normalized_threshold: float,
    expected_codes: list[str],
) -> None:
    provider, scorer = _configured_provider()
    assert provider._normalize_volume_threshold(float(raw_threshold)) == expected_normalized_threshold

    result = provider(
        _history("CONFIG-EDGE", volumes=[100.0] * 20 + [latest_volume]),
        {"filters": {"volume_ratio_min": raw_threshold}},
        top_n=5,
    )

    assert [item["stock_code"] for item in result] == expected_codes
    assert _codes(scorer.inputs) == expected_codes


@pytest.mark.parametrize(
    "filters",
    [
        {"price_change_min": "not-a-number"},
        {"volume_ratio_min": "not-a-number"},
    ],
)
def test_invalid_filter_config_raises_before_per_stock_scorer_catch(filters: dict[str, str]) -> None:
    history = pd.concat(
        [_history("FIRST"), _history("SECOND")],
        ignore_index=True,
    )
    provider, scorer = _configured_provider()

    with pytest.raises(ValueError):
        provider(history, {"filters": filters}, top_n=10)

    assert scorer.inputs == []


def test_scorer_exception_skips_only_that_stock_after_fast_filters() -> None:
    history = pd.concat(
        [_history("BROKEN"), _history("SURVIVOR")],
        ignore_index=True,
    )
    scorer = _RecordingScorer(fail_codes={"BROKEN"})
    provider, _ = _configured_provider(scorer)

    result = provider(history, {"filters": {"price_change_min": "0"}}, top_n=10)

    assert _codes(scorer.inputs) == ["BROKEN", "SURVIVOR"]
    assert [item["stock_code"] for item in result] == ["SURVIVOR"]


def test_replay_wrapper_removes_future_and_nat_availability_rows_before_provider() -> None:
    dates = pd.date_range("2026-08-12", periods=21, freq="D")
    numeric_dates = [int(value.strftime("%Y%m%d")) for value in dates]
    nat_availability = list(numeric_dates)
    nat_availability[-1] = pd.NaT
    future_availability = list(numeric_dates)
    future_availability[-1] = 20260902
    history = pd.concat(
        [
            _history("VALID", available_dates=numeric_dates),
            _history("NAT-POISON", available_dates=nat_availability),
            _history("FUTURE-POISON", available_dates=future_availability),
        ],
        ignore_index=True,
    )
    concrete_provider, scorer = _configured_provider()
    recording_provider = _RecordingProvider(concrete_provider)

    snapshot = RecommendationReplayService(recording_provider).run_snapshot(
        as_of_date="2026-09-01",
        profile_id="c1a-availability",
        config={},
        history=history,
        universe=None,
        top_n=10,
    )

    received = recording_provider.inputs[0]
    counts = received.groupby("證券代號").size().to_dict()
    assert counts == {"FUTURE-POISON": 20, "NAT-POISON": 20, "VALID": 21}
    assert received["日期"].max() == pd.Timestamp("2026-09-01")
    assert received["available_date"].notna().all()
    assert all(int(value) <= 20260901 for value in received["available_date"])
    assert {len(frame) for frame in scorer.inputs if str(frame["證券代號"].iloc[0]) == "VALID"} == {21}
    assert snapshot.diagnostics == ["unavailable_rows_excluded:2"]


@pytest.mark.parametrize("invalid_filter", ["price_change_min", "volume_ratio_min"])
def test_nineteen_rows_skip_before_filter_threshold_conversion(invalid_filter: str) -> None:
    calls: list[str] = []
    filters = {invalid_filter: _FloatProbe(invalid_filter, calls, fail=True)}
    provider, scorer = _configured_provider()

    result = provider(
        _history("SHORT", closes=[100.0] * 19),
        {"filters": filters},
        top_n=5,
    )

    assert result == []
    assert calls == []
    assert scorer.inputs == []


@pytest.mark.parametrize("later_invalid_filter", ["price_change_max", "volume_ratio_min"])
def test_price_min_rejection_precedes_later_invalid_threshold_conversion(
    later_invalid_filter: str,
) -> None:
    calls: list[str] = []
    filters: dict[str, object] = {
        "price_change_min": _FloatProbe("price_change_min", calls, value=100.0),
        later_invalid_filter: _FloatProbe(later_invalid_filter, calls, fail=True),
    }
    provider, scorer = _configured_provider()

    result = provider(
        _history("PRICE-REJECTS-FIRST"),
        {"filters": filters},
        top_n=5,
    )

    assert result == []
    assert calls == ["price_change_min"]
    assert scorer.inputs == []


@pytest.mark.parametrize("invalid_filter", ["price_change_max", "volume_ratio_min"])
def test_price_pass_then_later_invalid_threshold_raises_at_legacy_conversion_order(
    invalid_filter: str,
) -> None:
    calls: list[str] = []
    filters: dict[str, object] = {
        "price_change_min": _FloatProbe("price_change_min", calls, value=0.0),
    }
    if invalid_filter == "price_change_max":
        filters["price_change_max"] = _FloatProbe("price_change_max", calls, fail=True)
        filters["volume_ratio_min"] = _FloatProbe("volume_ratio_min", calls, fail=True)
        expected_calls = ["price_change_min", "price_change_max"]
    else:
        filters["volume_ratio_min"] = _FloatProbe("volume_ratio_min", calls, fail=True)
        expected_calls = ["price_change_min", "volume_ratio_min"]

    provider, scorer = _configured_provider()

    with pytest.raises(ValueError, match="synthetic invalid filter value"):
        provider(
            _history("PRICE-PASSES"),
            {"filters": filters},
            top_n=5,
        )

    assert calls == expected_calls
    assert scorer.inputs == []


def test_invalid_volume_threshold_is_not_converted_for_twenty_row_history() -> None:
    calls: list[str] = []
    provider, scorer = _configured_provider()

    result = provider(
        _history("TWENTY-ROWS", closes=[100.0] * 20),
        {"filters": {"volume_ratio_min": _FloatProbe("volume_ratio_min", calls, fail=True)}},
        top_n=5,
    )

    assert [item["stock_code"] for item in result] == ["TWENTY-ROWS"]
    assert calls == []
    assert _codes(scorer.inputs) == ["TWENTY-ROWS"]


def test_invalid_volume_threshold_is_not_converted_without_volume_column() -> None:
    calls: list[str] = []
    provider, scorer = _configured_provider()
    history = _history("NO-VOLUME-COLUMN").drop(columns=["成交股數"])

    result = provider(
        history,
        {"filters": {"volume_ratio_min": _FloatProbe("volume_ratio_min", calls, fail=True)}},
        top_n=5,
    )

    assert [item["stock_code"] for item in result] == ["NO-VOLUME-COLUMN"]
    assert calls == []
    assert _codes(scorer.inputs) == ["NO-VOLUME-COLUMN"]
