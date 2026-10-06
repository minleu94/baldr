from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import platform
import sys
from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from typing import Any, Callable, cast

import numpy as np
import pandas as pd
import pytest

from app_module.recommendation_dataframe_provider import (
    RecommendationDataFrameProvider,
    _resolve_numpy_rank_warning,
)
from app_module.recommendation_replay_service import RecommendationReplayService
from app_module.recommendation.replay_numeric_projection import (
    ReplayThresholdUnit,
    project_legacy_comparison_pair,
)
from decision_module.recommendation.replay_prefilter import (
    ReplayFastFilterPolicyV1,
    ReplayMetricStatus,
    ReplayPrefilterObservations,
    ReplayThreshold,
    ReplayVolumeThresholdV1,
    evaluate_replay_prefilter,
)


_AS_OF = date(2026, 9, 6)  # 週日 cutoff；資料最後交易日是週五 9/4。


@dataclass(frozen=True, slots=True)
class _ObservedTerminal:
    """記錄一次 runtime 原生／staged operation 的完整 terminal。"""

    logical_locus: str
    kind: str
    returned_bool: bool | None = None
    exception_type: str | None = None
    exception_message: str | None = None
    non_bool_type: str | None = None
    non_bool_repr: str | None = None


def _observe_terminal(
    logical_locus: str,
    operation: Callable[[], object],
) -> _ObservedTerminal:
    """把 return 與 exception 分開保留，絕不把例外轉成 False/None。"""

    try:
        result = operation()
    except Exception as exc:
        return _ObservedTerminal(
            logical_locus=logical_locus,
            kind="exception",
            exception_type=f"{type(exc).__module__}.{type(exc).__qualname__}",
            exception_message=str(exc),
        )
    if type(result) is bool:
        return _ObservedTerminal(
            logical_locus=logical_locus,
            kind="bool",
            returned_bool=result,
        )
    return _ObservedTerminal(
        logical_locus=logical_locus,
        kind="non_bool_return",
        non_bool_type=f"{type(result).__module__}.{type(result).__qualname__}",
        non_bool_repr=repr(result),
    )


class _RecordingScorer:
    def __init__(self, *, scores: dict[str, int] | None = None) -> None:
        self.calls: list[str] = []
        self.scores = scores or {}

    def generate_recommendations(self, stock_data: pd.DataFrame, config: dict) -> pd.DataFrame:
        code = str(stock_data["證券代號"].iloc[0])
        self.calls.append(code)
        result = stock_data.copy(deep=True)
        result["FinalScore"] = self.scores.get(code, 80)
        return result


class _FixedReasonEngine:
    def generate_reasons(self, latest_row: pd.Series, config: dict) -> list[str]:
        return ["runtime-oracle"]

    def format_reason_text(self, reasons: list[str], max_reasons: int = 3) -> str:
        return "|".join(reasons[:max_reasons])


class _LegacyFloatProbe:
    """測試專用 raw config，紀錄舊版 float() 的 lazy 順序。"""

    def __init__(
        self,
        label: str,
        calls: list[str],
        value: float | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.label = label
        self.calls = calls
        self.value = value
        self.error = error

    def __float__(self) -> float:
        self.calls.append(self.label)
        if self.error is not None:
            raise type(self.error)(str(self.error))
        if self.value is None:
            raise ValueError(f"legacy threshold missing: {self.label}")
        return self.value


def _configured_provider(
    scorer: _RecordingScorer | None = None,
) -> tuple[RecommendationDataFrameProvider, _RecordingScorer]:
    actual_scorer = scorer or _RecordingScorer()
    provider = RecommendationDataFrameProvider()
    setattr(provider, "strategy_configurator", actual_scorer)
    setattr(provider, "reason_engine", _FixedReasonEngine())
    return provider, actual_scorer


def _history(
    code: str,
    *,
    rows: int,
    dtype: str = "float64",
    close_values: Sequence[object] | None = None,
    volume_values: Sequence[object] | None = None,
    available_values: Sequence[object] | None = None,
    start: str = "2026-08-15",
) -> pd.DataFrame:
    dates = pd.date_range(start, periods=rows, freq="D")
    closes = close_values if close_values is not None else [100] * (rows - 1) + [101]
    volumes = volume_values if volume_values is not None else [100] * rows
    if len(closes) != rows or len(volumes) != rows:
        raise ValueError("synthetic values must match row count")
    result = pd.DataFrame(
        {
            "日期": [int(value.strftime("%Y%m%d")) for value in dates],
            "available_date": (
                available_values
                if available_values is not None
                else [int(value.strftime("%Y%m%d")) for value in dates]
            ),
            "證券代號": [code] * rows,
            "證券名稱": [f"name-{code}"] * rows,
            "收盤價": np.asarray(closes, dtype=dtype),
            "成交股數": np.asarray(volumes, dtype=dtype),
        }
    )
    return result


def _legacy_native_filter(
    stock_df: pd.DataFrame,
    filters: Mapping[str, object],
) -> bool:
    """凍結的測試 oracle：直接照舊 NumPy/Pandas scalar `<`/`>` 執行。"""

    # Provider 在 fast-filter 前已略過少於 20 列的股票；這個 oracle 不解析門檻。
    if len(stock_df) < 20:
        return False
    if not filters:
        return True

    close_col = next(
        (name for name in ("收盤價", "Close", "close") if name in stock_df.columns),
        None,
    )
    price_change: object | None = None
    if close_col is not None and len(stock_df) >= 2:
        previous = pd.to_numeric(stock_df.iloc[-2].get(close_col, 0), errors="coerce")
        current = pd.to_numeric(stock_df.iloc[-1].get(close_col, 0), errors="coerce")
        price_change = (
            ((current - previous) / previous * 100)
            if previous and not pd.isna(previous)
            else 0
        )

    price_min = filters.get("price_change_min") if close_col is not None else None
    price_max = filters.get("price_change_max") if close_col is not None else None
    if price_min is not None and price_change is not None:
        # 先 min；拒絕時 max/volume 的 float conversion 不應執行。
        if cast(Any, price_change) < float(cast(Any, price_min)):
            return False
    if price_max is not None and price_change is not None:
        if cast(Any, price_change) > float(cast(Any, price_max)):
            return False

    volume_col = next(
        (
            name
            for name in ("成交股數", "成交量", "Volume", "volume")
            if name in stock_df.columns
        ),
        None,
    )
    volume_min = filters.get("volume_ratio_min")
    if volume_col is not None and volume_min is not None and len(stock_df) >= 21:
        latest_volume = pd.to_numeric(stock_df[volume_col].iloc[-1], errors="coerce")
        average_volume = pd.to_numeric(
            stock_df[volume_col].iloc[-21:-1], errors="coerce"
        ).mean()
        volume_change = (
            ((latest_volume / average_volume) - 1) * 100
            if average_volume and not pd.isna(average_volume)
            else 0
        )
        volume_threshold = float(cast(Any, volume_min))
        # 此為舊 provider 的 Python float 正規化；不經 production helper。
        if -50 <= volume_threshold <= 10:
            volume_threshold = (volume_threshold - 1) * 100
        if volume_change < volume_threshold:
            return False
    return True


def _staged_reject(
    metric: object,
    threshold: float,
    *,
    maximum: bool = False,
    volume: bool = False,
) -> bool:
    unit = (
        ReplayThresholdUnit.VOLUME_EFFECTIVE_CHANGE_PERCENT
        if volume
        else ReplayThresholdUnit.PRICE_CHANGE_PERCENT
    )
    pair = project_legacy_comparison_pair(metric, threshold, unit=unit)
    if volume:
        observations = ReplayPrefilterObservations(
            stock_code="DIFFERENTIAL",
            as_of_date=_AS_OF,
            history_rows=21,
            maximum_row_date=_AS_OF,
            availability_column_present=False,
            maximum_available_date=None,
            price_change_status=ReplayMetricStatus.MISSING_COLUMN,
            volume_change_status=ReplayMetricStatus.AVAILABLE,
            volume_change_percent=pair.metric,
        )
        policy = ReplayFastFilterPolicyV1(
            volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
                ReplayThreshold.enabled(pair.threshold)
            )
        )
    else:
        observations = ReplayPrefilterObservations(
            stock_code="DIFFERENTIAL",
            as_of_date=_AS_OF,
            history_rows=20,
            maximum_row_date=_AS_OF,
            availability_column_present=False,
            maximum_available_date=None,
            price_change_status=ReplayMetricStatus.AVAILABLE,
            price_change_percent=pair.metric,
            volume_change_status=ReplayMetricStatus.MISSING_COLUMN,
        )
        policy = ReplayFastFilterPolicyV1(
            price_change_max=(
                ReplayThreshold.enabled(pair.threshold)
                if maximum
                else ReplayThreshold.disabled()
            ),
            price_change_min=(
                ReplayThreshold.disabled()
                if maximum
                else ReplayThreshold.enabled(pair.threshold)
            ),
        )
    result = evaluate_replay_prefilter(policy, observations)
    return result.disposition.value == "reject"


def _legacy_codes_after_cutoff(
    history: pd.DataFrame,
    *,
    as_of: date,
    filters: Mapping[str, object],
) -> tuple[list[str], list[str], list[str]]:
    """以原 native operators 從來源 frame 得到 call order 與通過候選。"""

    data = history.copy(deep=True)
    def parse_yyyymmdd(values: pd.Series) -> pd.Series:
        normalized = values.map(
            lambda value: (
                f"{int(value):08d}"
                if pd.notna(value) and str(value).strip()
                else None
            )
        )
        return pd.to_datetime(normalized, format="%Y%m%d", errors="coerce")

    parsed_dates = parse_yyyymmdd(data["日期"])
    data = data.loc[parsed_dates.notna() & (parsed_dates <= pd.Timestamp(as_of))].copy()
    data["日期"] = parsed_dates.loc[data.index]
    diagnostics: list[str] = []
    if "available_date" in data:
        available = parse_yyyymmdd(data["available_date"])
        unavailable = available.isna() | (available > pd.Timestamp(as_of))
        unavailable_count = int(unavailable.sum())
        if unavailable_count:
            diagnostics.append(f"unavailable_rows_excluded:{unavailable_count}")
        data = data.loc[~unavailable].copy()

    source_codes = list(data["證券代號"].dropna().astype(str).unique())
    scorer_order: list[str] = []
    eligible_codes: list[str] = []
    for code in source_codes:
        candidate = data.loc[data["證券代號"].astype(str) == code].sort_values(
            "日期"
        ).reset_index(drop=True)
        if _legacy_native_filter(candidate, filters):
            scorer_order.append(code)
            eligible_codes.append(code)
    return scorer_order, eligible_codes, diagnostics


@pytest.fixture
def runtime_fingerprint(record_property: Callable[[str, str], None]) -> dict[str, Any]:
    longdouble = np.dtype(np.longdouble)
    longdouble_info = np.finfo(longdouble)
    fingerprint: dict[str, Any] = {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "os": platform.platform(),
        "machine": platform.machine(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "longdouble": {
            "dtype_str": longdouble.str,
            "itemsize": int(longdouble.itemsize),
            "nmant": int(longdouble_info.nmant),
            "minexp": int(longdouble_info.minexp),
            "maxexp": int(longdouble_info.maxexp),
        },
    }
    encoded = json.dumps(fingerprint, sort_keys=True, separators=(",", ":"))
    record_property("tmp_num_01_runtime_fingerprint", encoded)
    print(f"TMP-NUM-01 runtime fingerprint: {encoded}")
    return fingerprint


def test_runtime_fingerprint_records_numeric_capabilities(
    runtime_fingerprint: dict[str, Any],
) -> None:
    assert runtime_fingerprint["python"] == sys.version.split()[0]
    assert runtime_fingerprint["numpy"] == np.__version__
    assert runtime_fingerprint["pandas"] == pd.__version__
    assert runtime_fingerprint["longdouble"]["itemsize"] == np.dtype(np.longdouble).itemsize


def test_rank_warning_resolver_prefers_numpy_2_api_without_reading_legacy_alias() -> None:
    class NewRankWarning(Warning):
        pass

    class Numpy2Shape:
        exceptions = SimpleNamespace(RankWarning=NewRankWarning)

        @property
        def RankWarning(self) -> type[Warning]:
            raise AssertionError("NumPy 2 API must not evaluate the legacy fallback")

    assert _resolve_numpy_rank_warning(Numpy2Shape()) is NewRankWarning


def test_rank_warning_resolver_lazily_falls_back_to_numpy_1_api() -> None:
    class LegacyRankWarning(Warning):
        pass

    class Numpy1Shape:
        exceptions = SimpleNamespace()
        RankWarning = LegacyRankWarning

    assert _resolve_numpy_rank_warning(Numpy1Shape()) is LegacyRankWarning


def test_real_no_filter_provider_candidate_is_scored_under_current_rank_warning_api() -> None:
    provider, scorer = _configured_provider()
    history = _history("RANK-WARNING", rows=21)

    result = provider.run_with_as_of_handoff(
        history,
        {},
        5,
        _AS_OF,
    )

    assert [row["stock_code"] for row in result.rows] == ["RANK-WARNING"]
    assert scorer.calls == ["RANK-WARNING"]
    assert result.compatibility_scoring_outcomes == ()
    assert len(result.scoring_outcomes) == 1
    assert result.scoring_outcomes == (None,)


@pytest.mark.parametrize(
    ("metric", "threshold", "operator_name"),
    [
        pytest.param(np.float16(1), 1.0001, "<", id="float16-weak-threshold"),
        pytest.param(np.float32(1), 1.00000001, "<", id="float32-weak-threshold"),
        pytest.param(np.float64(10.100000000000001), 10.1, ">", id="float64-ulp"),
        pytest.param(np.int64(2**53 + 1), float(2**53), ">", id="int64-weak-promotion"),
        pytest.param(np.float64(float("nan")), 0.0, "<", id="nan-unordered-min"),
        pytest.param(np.float64(float("nan")), 0.0, ">", id="nan-unordered-max"),
        pytest.param(np.float16(float("inf")), 1e100, ">", id="float16-positive-infinity"),
        pytest.param(np.float64(float("-inf")), -1e100, "<", id="negative-infinity"),
        pytest.param(np.complex64(complex(1, 1)), 1.0, ">", id="complex-lexicographic"),
        pytest.param(np.complex64(complex(1, float("nan"))), 1.0, "<", id="complex-nan-component"),
    ],
)
def test_native_scalar_operator_is_differential_oracle_for_staged_filter(
    metric: object,
    threshold: float,
    operator_name: str,
) -> None:
    native_metric = cast(Any, metric)
    logical_locus = "price_change_min" if operator_name == "<" else "price_change_max"
    with np.errstate(over="ignore"):
        if operator_name == "<":
            legacy_terminal = _observe_terminal(
                logical_locus,
                lambda: bool(native_metric < threshold),
            )
        else:
            legacy_terminal = _observe_terminal(
                logical_locus,
                lambda: bool(native_metric > threshold),
            )
        staged_terminal = _observe_terminal(
            logical_locus,
            lambda: _staged_reject(
                metric,
                threshold,
                maximum=operator_name == ">",
            ),
        )
    assert staged_terminal == legacy_terminal


def test_python_complex_error_type_and_operator_locus_match_legacy() -> None:
    metric = complex(1, 0)
    threshold = 1.0
    native_terminal = _observe_terminal(
        "price_change_min",
        lambda: bool(cast(Any, metric) < threshold),
    )

    def staged_operation() -> bool:
        pair = project_legacy_comparison_pair(
            metric,
            threshold,
            unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
        )
        observations = ReplayPrefilterObservations(
            stock_code="PY-COMPLEX",
            as_of_date=_AS_OF,
            history_rows=20,
            maximum_row_date=_AS_OF,
            availability_column_present=False,
            maximum_available_date=None,
            price_change_status=ReplayMetricStatus.AVAILABLE,
            price_change_percent=pair.metric,
            volume_change_status=ReplayMetricStatus.MISSING_COLUMN,
        )
        policy = ReplayFastFilterPolicyV1(
            price_change_min=ReplayThreshold.enabled(pair.threshold)
        )
        return evaluate_replay_prefilter(policy, observations).disposition.value == "reject"

    staged_terminal = _observe_terminal("price_change_min", staged_operation)
    assert native_terminal.kind == "exception"
    assert staged_terminal == native_terminal


def test_float16_overflow_locus_matches_legacy_native_operator() -> None:
    metric = np.float16(1)
    threshold = 1e100
    with np.errstate(over="raise"):
        legacy_terminal = _observe_terminal(
            "price_change_min",
            lambda: bool(metric < threshold),
        )
    with np.errstate(over="raise"):
        staged_terminal = _observe_terminal(
            "price_change_min",
            lambda: _staged_reject(metric, threshold),
        )
    assert staged_terminal == legacy_terminal


def test_terminal_observation_never_equates_exception_with_false_result() -> None:
    def raises_value_error() -> bool:
        raise ValueError("synthetic native terminal")

    returned_false = _observe_terminal("price_change_min", lambda: False)
    raised = _observe_terminal("price_change_min", raises_value_error)

    assert returned_false != raised
    assert returned_false.kind == "bool"
    assert returned_false.returned_bool is False
    assert raised.kind == "exception"
    assert raised.exception_type == "builtins.ValueError"
    assert raised.exception_message == "synthetic native terminal"
    assert raised.logical_locus == "price_change_min"


def test_native_volume_effective_percent_operator_matches_staged_pair() -> None:
    metric = np.float32(10.0)
    raw_ratio = "1.1000000191734864"
    # 舊 provider 順序：float(raw)，再僅一次轉成有效百分比。
    legacy_threshold = float(raw_ratio)
    if -50 <= legacy_threshold <= 10:
        legacy_threshold = (legacy_threshold - 1) * 100
    legacy_reject = bool(metric < legacy_threshold)
    staged_reject = _staged_reject(
        metric,
        legacy_threshold,
        volume=True,
    )
    assert staged_reject is legacy_reject


def test_threshold_conversion_order_and_exception_locus_match_native_oracle() -> None:
    history = _history("ORDER", rows=21, close_values=[100] * 20 + [101])

    oracle_calls: list[str] = []
    oracle_filters = {
        "price_change_min": _LegacyFloatProbe("price_min", oracle_calls, 100.0),
        "price_change_max": _LegacyFloatProbe(
            "price_max", oracle_calls, error=ValueError("bad max")
        ),
        "volume_ratio_min": _LegacyFloatProbe(
            "volume_min", oracle_calls, error=ValueError("bad volume")
        ),
    }
    oracle_terminal = _observe_terminal(
        "price_change_min",
        lambda: _legacy_native_filter(history, oracle_filters),
    )

    provider_calls: list[str] = []
    provider_filters = {
        "price_change_min": _LegacyFloatProbe("price_min", provider_calls, 100.0),
        "price_change_max": _LegacyFloatProbe(
            "price_max", provider_calls, error=ValueError("bad max")
        ),
        "volume_ratio_min": _LegacyFloatProbe(
            "volume_min", provider_calls, error=ValueError("bad volume")
        ),
    }
    provider, scorer = _configured_provider()
    provider_terminal = _observe_terminal(
        "price_change_min",
        lambda: bool(provider(history, {"filters": provider_filters}, top_n=10)),
    )

    assert oracle_terminal == provider_terminal
    assert oracle_terminal.kind == "bool"
    assert oracle_terminal.returned_bool is False
    assert oracle_calls == provider_calls == ["price_min"]
    assert scorer.calls == []


@pytest.mark.parametrize(
    ("rows", "volume_column", "expected_conversion_calls", "expected_score"),
    [
        (19, True, [], False),
        (20, True, ["price_min"], True),
        (21, False, ["price_min"], True),
        (21, True, ["price_min", "volume_min"], "raises"),
    ],
)
def test_history_count_and_missing_volume_keep_lazy_conversion_cutpoints(
    rows: int,
    volume_column: bool,
    expected_conversion_calls: list[str],
    expected_score: bool | str,
) -> None:
    history = _history("COUNT", rows=rows, close_values=[100] * (rows - 1) + [101])
    if not volume_column:
        history = history.drop(columns=["成交股數"])

    oracle_calls: list[str] = []
    oracle_filters = {
        "price_change_min": _LegacyFloatProbe("price_min", oracle_calls, 0.0),
        "volume_ratio_min": _LegacyFloatProbe(
            "volume_min", oracle_calls, error=ValueError("bad volume")
        ),
    }
    provider_calls: list[str] = []
    provider_filters = {
        "price_change_min": _LegacyFloatProbe("price_min", provider_calls, 0.0),
        "volume_ratio_min": _LegacyFloatProbe(
            "volume_min", provider_calls, error=ValueError("bad volume")
        ),
    }

    provider, scorer = _configured_provider()
    logical_locus = "minimum_history" if rows < 20 else "fast_filters"
    oracle_terminal = _observe_terminal(
        logical_locus,
        lambda: _legacy_native_filter(history, oracle_filters),
    )
    provider_terminal = _observe_terminal(
        logical_locus,
        lambda: bool(provider(history, {"filters": provider_filters}, top_n=5)),
    )

    assert provider_terminal == oracle_terminal
    if expected_score == "raises":
        assert oracle_terminal.kind == "exception"
        assert scorer.calls == []
    else:
        assert oracle_terminal.kind == "bool"
        assert oracle_terminal.returned_bool is expected_score
        assert scorer.calls == (["COUNT"] if expected_score else [])

    assert oracle_calls == provider_calls == expected_conversion_calls


def test_cutoff_availability_weekend_and_scorer_order_match_native_oracle() -> None:
    n19 = _history("N19", rows=20)
    n19.loc[n19.index[-1], "available_date"] = None
    n20 = _history("N20", rows=21)
    n20.loc[n20.index[-1], "available_date"] = 20260907
    n21 = _history("N21", rows=21, volume_values=[100] * 20 + [110])
    future_poison = _history(
        "N21",
        rows=1,
        close_values=[1000000],
        volume_values=[1000000],
        available_values=[20260907],
        start="2026-09-07",
    )
    history = pd.concat([n19, n20, n21, future_poison], ignore_index=True)
    filters: dict[str, object] = {
        "price_change_min": "0",
        "volume_ratio_min": "1.1",
    }
    expected_calls, expected_codes, expected_diagnostics = _legacy_codes_after_cutoff(
        history,
        as_of=_AS_OF,
        filters=filters,
    )
    provider, scorer = _configured_provider()
    snapshot = RecommendationReplayService(provider).run_snapshot(
        as_of_date=_AS_OF.isoformat(),
        profile_id="tmp-num-01-runtime-differential",
        config={"filters": filters},
        history=history,
        universe=None,
        top_n=10,
    )

    actual_codes = [row["stock_code"] for row in snapshot.recommendations]
    assert expected_calls == expected_codes == ["N20", "N21"]
    assert scorer.calls == expected_calls
    assert actual_codes == expected_codes
    assert snapshot.diagnostics == expected_diagnostics == [
        "unavailable_rows_excluded:2"
    ]
    assert snapshot.as_of_date == _AS_OF.isoformat()
    assert all(
        set(row)
        == {"stock_code", "stock_name", "total_score", "factor_scores", "selection_reason"}
        for row in snapshot.recommendations
    )


@pytest.mark.skipif(
    np.finfo(np.longdouble).nmant <= np.finfo(np.float64).nmant,
    reason="此 runtime 的 longdouble 沒有超過 float64 的 mantissa；較寬分支未覆蓋",
)
def test_wider_longdouble_round_trip_matches_native_runtime_operator() -> None:
    dtype = np.dtype(np.longdouble)
    metric = np.nextafter(dtype.type(1), dtype.type(2))
    threshold = 1.0
    legacy_reject = bool(metric > threshold)
    staged_reject = _staged_reject(metric, threshold, maximum=True)
    assert float(metric) == threshold
    assert legacy_reject is True
    assert staged_reject is legacy_reject
