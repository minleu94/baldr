from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app_module.recommendation_dataframe_provider import (
    RecommendationDataFrameProvider,
    _LegacyFastFilterTraceCapture,
    _LegacyFastFilterTraceEvent,
    _LegacyFastFilterTraceStage,
    _LegacyFastFilterTraceStatus,
    _capture_legacy_filter_value,
)
from app_module.recommendation_replay_service import RecommendationReplayService


class _RecordingScorer:
    def __init__(self) -> None:
        self.inputs: list[pd.DataFrame] = []

    def generate_recommendations(self, stock_data: pd.DataFrame, config: dict) -> pd.DataFrame:
        self.inputs.append(stock_data.copy(deep=True))
        result = stock_data.copy(deep=True)
        result["FinalScore"] = 80
        return result


class _FixedReasonEngine:
    def generate_reasons(self, latest_row: pd.Series, config: dict) -> list[str]:
        return ["synthetic"]

    def format_reason_text(self, reasons: list[str], max_reasons: int = 3) -> str:
        return "|".join(reasons[:max_reasons])


class _FloatProbe:
    def __init__(self, name: str, calls: list[str], value: float, *, fail: bool = False) -> None:
        self.name = name
        self.calls = calls
        self.value = value
        self.fail = fail

    def __float__(self) -> float:
        self.calls.append(self.name)
        if self.fail:
            raise ValueError(f"synthetic invalid filter value: {self.name}")
        return self.value


class _RecordingProvider:
    def __init__(self, provider: RecommendationDataFrameProvider) -> None:
        self.provider = provider
        self.inputs: list[pd.DataFrame] = []
        self.trace = _LegacyFastFilterTraceCapture()

    def __call__(self, data: pd.DataFrame, config: dict, top_n: int) -> list[dict]:
        self.inputs.append(data.copy(deep=True))
        return self.provider(data, config, top_n, capture_sink=self.trace)


def _configured_provider() -> tuple[RecommendationDataFrameProvider, _RecordingScorer]:
    scorer = _RecordingScorer()
    provider = RecommendationDataFrameProvider()
    provider.strategy_configurator = scorer
    provider.reason_engine = _FixedReasonEngine()
    return provider, scorer


def _history(
    stock_code: str,
    *,
    closes: list[float] | None = None,
    volumes: list[float] | None = None,
    available_dates: list[int] | None = None,
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


def _values(trace: _LegacyFastFilterTraceCapture) -> list[tuple[str, str, Decimal | None]]:
    return [
        (event.stage.value, event.status.value, event.value)
        for event in trace.events
    ]


def test_shadow_trace_preserves_minimum_reject_before_later_threshold_conversion() -> None:
    calls: list[str] = []
    provider, scorer = _configured_provider()
    trace = _LegacyFastFilterTraceCapture()
    history = _history("MIN-REJECTS", closes=[1000.0] * 19 + [1101.0])
    config = {
        "filters": {
            "price_change_min": _FloatProbe("price_min", calls, 100.0),
            "price_change_max": _FloatProbe("price_max", calls, 0.0, fail=True),
            "volume_ratio_min": _FloatProbe("volume_min", calls, 1.5, fail=True),
        }
    }

    result = provider(history, config, top_n=5, capture_sink=trace)

    assert result == []
    assert scorer.inputs == []
    assert calls == ["price_min"]
    assert _values(trace) == [
        (
            "price_change_metric",
            "finite",
            Decimal.from_float(10.100000000000001),
        ),
        ("price_change_min_threshold", "finite", Decimal.from_float(100.0)),
    ]


def test_shadow_trace_captures_float_metric_and_effective_volume_threshold_in_order() -> None:
    provider, scorer = _configured_provider()
    trace = _LegacyFastFilterTraceCapture()
    history = _history("VOLUME-1-1", volumes=[100.0] * 20 + [110.0])
    config = {"filters": {"volume_ratio_min": "1.1"}}

    result = provider(history, config, top_n=5, capture_sink=trace)

    assert [item["stock_code"] for item in result] == ["VOLUME-1-1"]
    assert [str(frame["證券代號"].iloc[0]) for frame in scorer.inputs] == ["VOLUME-1-1"]
    assert _values(trace) == [
        ("price_change_metric", "finite", Decimal.from_float(0.0)),
        (
            "volume_change_metric",
            "finite",
            Decimal.from_float(10.000000000000009),
        ),
        (
            "volume_change_min_effective_percent",
            "finite",
            Decimal.from_float(10.000000000000009),
        ),
    ]


def test_shadow_trace_records_legacy_volume_float_coercion_band_edges() -> None:
    cases = (
        ("10.0000000000000001", 110.0, 900.0, False),
        ("-50.000000000000001", 0.0, -5100.0, True),
    )

    for raw_threshold, latest_volume, effective_threshold, expected_pass in cases:
        provider, scorer = _configured_provider()
        trace = _LegacyFastFilterTraceCapture()
        result = provider(
            _history("VOLUME-BAND", volumes=[100.0] * 20 + [latest_volume]),
            {"filters": {"volume_ratio_min": raw_threshold}},
            top_n=5,
            capture_sink=trace,
        )

        assert bool(result) is expected_pass
        assert bool(scorer.inputs) is expected_pass
        assert trace.events[-1].stage is (
            _LegacyFastFilterTraceStage.VOLUME_CHANGE_MIN_EFFECTIVE_PERCENT
        )
        assert trace.events[-1].value == Decimal.from_float(effective_threshold)


def test_shadow_trace_marks_unordered_nan_and_keeps_legacy_pass_result() -> None:
    cases = (
        (
            _history("PRICE-NAN", closes=[100.0] * 19 + [np.nan]),
            {"filters": {"price_change_min": "5"}},
            _LegacyFastFilterTraceStage.PRICE_CHANGE_METRIC,
        ),
        (
            _history("VOLUME-NAN", volumes=[100.0] * 20 + [np.nan]),
            {"filters": {"volume_ratio_min": "1.5"}},
            _LegacyFastFilterTraceStage.VOLUME_CHANGE_METRIC,
        ),
    )

    for history, config, unordered_stage in cases:
        provider, scorer = _configured_provider()
        trace = _LegacyFastFilterTraceCapture()

        result = provider(history, config, top_n=5, capture_sink=trace)

        assert len(result) == 1
        assert len(scorer.inputs) == 1
        unordered = [event for event in trace.events if event.stage is unordered_stage]
        assert len(unordered) == 1
        assert unordered[0].status is _LegacyFastFilterTraceStatus.UNORDERED
        assert unordered[0].value is None
        assert trace.available is True


def test_shadow_trace_records_zero_denominators_as_zero_and_still_rejects() -> None:
    provider, scorer = _configured_provider()
    trace = _LegacyFastFilterTraceCapture()
    history = _history("ZERO-DENOM", closes=[100.0] * 18 + [0.0, 100.0])

    result = provider(
        history,
        {"filters": {"price_change_min": "1"}},
        top_n=5,
        capture_sink=trace,
    )

    assert result == []
    assert scorer.inputs == []
    assert _values(trace) == [
        ("price_change_metric", "finite", Decimal.from_float(0.0)),
        ("price_change_min_threshold", "finite", Decimal.from_float(1.0)),
    ]


def test_capture_failure_is_shadow_unavailable_and_does_not_change_provider_result() -> None:
    class _FailingEventList(list[_LegacyFastFilterTraceEvent]):
        def append(self, item: _LegacyFastFilterTraceEvent) -> None:
            raise RuntimeError("synthetic trace sink failure")

    provider, scorer = _configured_provider()
    trace = _LegacyFastFilterTraceCapture(events=_FailingEventList())

    result = provider(
        _history("SINK-FAIL"),
        {"filters": {"price_change_min": "0"}},
        top_n=5,
        capture_sink=trace,
    )

    assert [item["stock_code"] for item in result] == ["SINK-FAIL"]
    assert len(scorer.inputs) == 1
    assert trace.available is False


def test_legacy_filter_exception_marks_partial_trace_unavailable_and_reraises() -> None:
    calls: list[str] = []
    provider, scorer = _configured_provider()
    trace = _LegacyFastFilterTraceCapture()
    history = _history("INVALID-THRESHOLD")
    config = {
        "filters": {
            "price_change_min": _FloatProbe(
                "price_min", calls, 0.0, fail=True
            ),
            "price_change_max": _FloatProbe("price_max", calls, 10.0),
            "volume_ratio_min": _FloatProbe("volume_min", calls, 1.5),
        }
    }

    with pytest.raises(
        ValueError, match="synthetic invalid filter value: price_min"
    ):
        provider(history, config, top_n=5, capture_sink=trace)

    assert calls == ["price_min"]
    assert scorer.inputs == []
    assert trace.available is False
    assert _values(trace) == [
        ("price_change_metric", "finite", Decimal.from_float(0.0)),
    ]


def test_trace_conversion_failure_is_recorded_as_unavailable() -> None:
    class _BrokenFloat(float):
        def __float__(self) -> float:
            raise ValueError("synthetic trace conversion failure")

    trace = _LegacyFastFilterTraceCapture()
    _capture_legacy_filter_value(
        trace,
        "BROKEN-TRACE",
        _LegacyFastFilterTraceStage.PRICE_CHANGE_METRIC,
        _BrokenFloat(1.0),
    )

    assert trace.available is False
    assert trace.events == [
        _LegacyFastFilterTraceEvent(
            stock_code="BROKEN-TRACE",
            stage=_LegacyFastFilterTraceStage.PRICE_CHANGE_METRIC,
            status=_LegacyFastFilterTraceStatus.UNAVAILABLE,
            value=None,
        )
    ]


def test_trace_events_keep_candidate_identity_when_one_call_processes_many_stocks() -> None:
    provider, scorer = _configured_provider()
    trace = _LegacyFastFilterTraceCapture()
    history = pd.concat(
        [
            _history("FIRST"),
            _history("SECOND", closes=[100.0] * 19 + [101.0]),
        ],
        ignore_index=True,
    )

    result = provider(
        history,
        {"filters": {"price_change_min": "0"}},
        top_n=5,
        capture_sink=trace,
    )

    assert [item["stock_code"] for item in result] == ["FIRST", "SECOND"]
    assert [str(frame["證券代號"].iloc[0]) for frame in scorer.inputs] == [
        "FIRST",
        "SECOND",
    ]
    assert [event.stock_code for event in trace.events] == [
        "FIRST",
        "FIRST",
        "SECOND",
        "SECOND",
    ]
    assert [event.stage for event in trace.events] == [
        _LegacyFastFilterTraceStage.PRICE_CHANGE_METRIC,
        _LegacyFastFilterTraceStage.PRICE_CHANGE_MIN_THRESHOLD,
        _LegacyFastFilterTraceStage.PRICE_CHANGE_METRIC,
        _LegacyFastFilterTraceStage.PRICE_CHANGE_MIN_THRESHOLD,
    ]


def test_same_provider_invocation_traces_only_cutoff_and_available_rows() -> None:
    dates = pd.date_range("2026-08-12", periods=21, freq="D")
    available_dates = [int(value.strftime("%Y%m%d")) for value in dates]
    history = _history(
        "CUTOFF-POISON",
        available_dates=available_dates,
    )
    same_day_unavailable = _history(
        "CUTOFF-POISON",
        closes=[100.0],
        volumes=[10000.0],
        available_dates=[20260902],
    )
    same_day_unavailable.loc[:, "日期"] = 20260831
    future_date = _history(
        "CUTOFF-POISON",
        closes=[1000.0],
        volumes=[20000.0],
        available_dates=[20260902],
    )
    future_date.loc[:, "日期"] = 20260902
    source = pd.concat([history, same_day_unavailable, future_date], ignore_index=True)
    provider, scorer = _configured_provider()
    recording = _RecordingProvider(provider)

    snapshot = RecommendationReplayService(recording).run_snapshot(
        as_of_date="2026-09-01",
        profile_id="c1a-shadow-cutoff",
        config={
            "filters": {
                "price_change_min": "0",
                "volume_ratio_min": "1.5",
            }
        },
        history=source,
        universe=None,
        top_n=5,
    )

    assert snapshot.diagnostics == ["unavailable_rows_excluded:1"]
    assert len(recording.inputs) == 1
    received = recording.inputs[0]
    assert len(received) == 21
    assert received["日期"].max() == pd.Timestamp("2026-09-01")
    assert received["available_date"].max() == 20260901
    assert (received["available_date"] <= 20260901).all()
    assert scorer.inputs == []
    assert [
        (event.stage, event.status, event.value)
        for event in recording.trace.events
    ] == [
        (
            _LegacyFastFilterTraceStage.PRICE_CHANGE_METRIC,
            _LegacyFastFilterTraceStatus.FINITE,
            Decimal.from_float(0.0),
        ),
        (
            _LegacyFastFilterTraceStage.PRICE_CHANGE_MIN_THRESHOLD,
            _LegacyFastFilterTraceStatus.FINITE,
            Decimal.from_float(0.0),
        ),
        (
            _LegacyFastFilterTraceStage.VOLUME_CHANGE_METRIC,
            _LegacyFastFilterTraceStatus.FINITE,
            Decimal.from_float(0.0),
        ),
        (
            _LegacyFastFilterTraceStage.VOLUME_CHANGE_MIN_EFFECTIVE_PERCENT,
            _LegacyFastFilterTraceStatus.FINITE,
            Decimal.from_float(50.0),
        ),
    ]
