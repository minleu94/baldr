from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
from threading import Barrier, Lock
from typing import Any

import pandas as pd

from app_module.recommendation_dataframe_provider import RecommendationDataFrameProvider
from app_module.recommendation_replay_service import RecommendationReplayService


class _AsOfAwareProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[pd.DataFrame, dict[str, Any], int, date]] = []

    def __call__(self, data: pd.DataFrame, config: dict[str, Any], top_n: int) -> list[dict[str, Any]]:
        raise AssertionError("as-of aware provider 應走 run_with_as_of")

    def run_with_as_of(
        self,
        data: pd.DataFrame,
        config: dict[str, Any],
        top_n: int,
        as_of_date: date,
    ) -> list[dict[str, Any]]:
        self.calls.append((data.copy(deep=True), deepcopy(config), top_n, as_of_date))
        return []


class _ThreeArgumentProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[pd.DataFrame, dict[str, Any], int]] = []

    def __call__(self, data: pd.DataFrame, config: dict[str, Any], top_n: int) -> list[dict[str, Any]]:
        self.calls.append((data.copy(deep=True), deepcopy(config), top_n))
        return []


def _history(
    dates: list[int],
    stock_codes: list[str],
    available_dates: list[object] | None = None,
) -> pd.DataFrame:
    frame: dict[str, object] = {
        "日期": dates,
        "證券代號": stock_codes,
        "證券名稱": [f"name-{code}" for code in stock_codes],
    }
    if available_dates is not None:
        frame["available_date"] = pd.Series(available_dates, dtype="object")
    return pd.DataFrame(frame)


def test_weekend_cutoff_is_forwarded_even_when_last_row_is_friday() -> None:
    provider = _AsOfAwareProvider()
    history = _history([20260904], ["FRIDAY"], [20260904])
    config = {"regime": "neutral", "nested": {"threshold": 5}}

    snapshot = RecommendationReplayService(provider).run_snapshot(
        as_of_date="2026-09-06",
        profile_id="as-of-weekend",
        config=config,
        history=history,
        universe=None,
        top_n=7,
    )

    received, received_config, received_top_n, received_cutoff = provider.calls[0]
    assert received_cutoff == date(2026, 9, 6)
    assert received["日期"].max().date() == date(2026, 9, 4)
    assert received_config == config
    assert received_top_n == 7
    assert snapshot.as_of_date == "2026-09-06"
    assert snapshot.strategy_config == config
    assert config == {"regime": "neutral", "nested": {"threshold": 5}}


def test_availability_poison_is_removed_before_as_of_provider_and_universe() -> None:
    provider = _AsOfAwareProvider()
    history = _history(
        [20260904, 20260904, 20260904, 20260904, 20260907],
        [
            "KEEP",
            "NAT-AVAIL",
            "FUTURE-AVAIL",
            "OUTSIDE-UNIVERSE",
            "FUTURE-ROW",
        ],
        [20260904, None, 20260907, None, 20260907],
    )

    snapshot = RecommendationReplayService(provider).run_snapshot(
        as_of_date="2026-09-06",
        profile_id="as-of-availability",
        config={},
        history=history,
        universe=["KEEP", "NAT-AVAIL", "FUTURE-AVAIL", "FUTURE-ROW"],
        top_n=5,
    )

    received, _, _, received_cutoff = provider.calls[0]
    assert received_cutoff == date(2026, 9, 6)
    assert received["證券代號"].tolist() == ["KEEP"]
    assert received["available_date"].tolist() == [20260904]
    assert received["日期"].max().date() == date(2026, 9, 4)
    # Availability diagnostics run before universe selection, so even an
    # unavailable stock outside the requested universe remains counted.
    assert snapshot.diagnostics == ["unavailable_rows_excluded:3"]


def test_ordinary_three_argument_provider_keeps_existing_call_contract() -> None:
    provider = _ThreeArgumentProvider()
    history = _history([20260904, 20260907], ["KEEP", "FUTURE"])
    config = {"regime": "neutral"}

    snapshot = RecommendationReplayService(provider).run_snapshot(
        as_of_date="2026-09-06",
        profile_id="legacy-three-arg",
        config=config,
        history=history,
        universe=None,
        top_n=3,
    )

    received, received_config, received_top_n = provider.calls[0]
    assert received["證券代號"].tolist() == ["KEEP"]
    assert received_config == config
    assert received_top_n == 3
    assert snapshot.as_of_date == "2026-09-06"
    assert snapshot.strategy_config == config


class _EmptyScorer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate_recommendations(self, stock_data: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
        self.calls.append(str(stock_data["證券代號"].iloc[0]))
        return stock_data.iloc[0:0].copy()


class _EmptyReasonEngine:
    def generate_reasons(self, latest_row: pd.Series, config: dict[str, Any]) -> list[str]:
        return []

    def format_reason_text(self, reasons: list[str], max_reasons: int = 3) -> str:
        return ""


class _ContextRecordingProvider(RecommendationDataFrameProvider):
    def __init__(self, barrier: Barrier) -> None:
        super().__init__()
        self.barrier = barrier
        self.context_lock = Lock()
        self.contexts: list[tuple[date, date]] = []
        self.scorer = _EmptyScorer()
        self.strategy_configurator = self.scorer
        self.reason_engine = _EmptyReasonEngine()

    def __call__(
        self,
        as_of_data: pd.DataFrame,
        config: dict[str, Any],
        top_n: int,
        *,
        capture_sink: Any = None,
        _call_context: Any = None,
    ) -> list[dict[str, Any]]:
        assert _call_context is not None
        assert type(_call_context.as_of_date) is date
        self.barrier.wait(timeout=10)
        maximum_row_date = as_of_data["日期"].max().date()
        with self.context_lock:
            self.contexts.append((_call_context.as_of_date, maximum_row_date))
        return super().__call__(
            as_of_data,
            config,
            top_n,
            capture_sink=capture_sink,
            _call_context=_call_context,
        )


def test_same_provider_instance_keeps_concurrent_requested_cutoffs_call_local() -> None:
    dates = pd.date_range("2026-08-01", periods=21, freq="D")
    history = _history(
        [int(value.strftime("%Y%m%d")) for value in dates],
        ["SAME"] * len(dates),
    )
    provider = _ContextRecordingProvider(Barrier(2))
    service = RecommendationReplayService(provider)

    with ThreadPoolExecutor(max_workers=2) as executor:
        saturday = executor.submit(
            service.run_snapshot,
            "2026-08-22",
            "as-of-saturday",
            {},
            history,
            None,
            5,
        )
        sunday = executor.submit(
            service.run_snapshot,
            "2026-08-23",
            "as-of-sunday",
            {},
            history,
            None,
            5,
        )
        saturday_snapshot = saturday.result(timeout=15)
        sunday_snapshot = sunday.result(timeout=15)

    assert sorted(provider.contexts) == [
        (date(2026, 8, 22), date(2026, 8, 21)),
        (date(2026, 8, 23), date(2026, 8, 21)),
    ]
    assert len(provider.scorer.calls) == 2
    assert saturday_snapshot.as_of_date == "2026-08-22"
    assert sunday_snapshot.as_of_date == "2026-08-23"
    assert not hasattr(provider, "_as_of_date")
