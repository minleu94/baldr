from __future__ import annotations

from copy import deepcopy
import pandas as pd
import pytest

from app_module.recommendation_dataframe_provider import RecommendationDataFrameProvider
from app_module.recommendation_portfolio_backtest_service import (
    RecommendationPortfolioBacktestService,
)
from app_module.recommendation_portfolio_dtos import RecommendationSnapshotDTO
from app_module.recommendation_replay_service import RecommendationReplayService


class _ScoreFromFixture:
    """依 fixture 欄位回傳 legacy score，避免用固定分數掩蓋 cutoff 差異。"""

    def __init__(self, *, fail_codes: set[str] | None = None) -> None:
        self.inputs: list[pd.DataFrame] = []
        self.fail_codes = fail_codes or set()

    def generate_recommendations(self, stock_data: pd.DataFrame, config: dict) -> pd.DataFrame:
        self.inputs.append(stock_data.copy(deep=True))
        stock_code = str(stock_data["證券代號"].iloc[0])
        if stock_code in self.fail_codes:
            raise RuntimeError(f"fixture scorer failed for {stock_code}")
        result = stock_data.copy()
        result["FinalScore"] = pd.to_numeric(result["oracle_score"], errors="raise")
        return result


class _FixedReasonEngine:
    def generate_reasons(self, latest_row: pd.Series, config: dict) -> list[str]:
        return ["fixture_reason"]

    def format_reason_text(self, reasons: list[str], max_reasons: int = 3) -> str:
        return "|".join(reasons[:max_reasons])


class _RecordingProvider:
    def __init__(self, provider) -> None:
        self.provider = provider
        self.calls: list[tuple[pd.DataFrame, dict, int]] = []

    def __call__(self, data: pd.DataFrame, config: dict, top_n: int) -> list[dict]:
        self.calls.append((data.copy(deep=True), deepcopy(config), top_n))
        return self.provider(data, config, top_n)


def _configured_provider(scorer: _ScoreFromFixture | None = None) -> tuple[RecommendationDataFrameProvider, _ScoreFromFixture]:
    actual_scorer = scorer or _ScoreFromFixture()
    provider = RecommendationDataFrameProvider()
    provider.strategy_configurator = actual_scorer
    provider.reason_engine = _FixedReasonEngine()
    return provider, actual_scorer


def _yyyymmdd(value: object) -> int:
    return int(pd.Timestamp(value).strftime("%Y%m%d"))


def _stock_history(
    stock_code: str,
    dates: list[object],
    *,
    stock_name: str | None = None,
    score_values: list[int | float] | None = None,
    component_scores: tuple[int | float, int | float, int | float, int | float, int | float] = (
        10,
        20,
        30,
        40,
        50,
    ),
    close_prices: list[int | float] | None = None,
    volumes: list[int | float] | None = None,
    available_dates: list[int | None] | None = None,
) -> pd.DataFrame:
    if score_values is None:
        score_values = [50] * len(dates)
    if close_prices is None:
        close_prices = [100 + index for index in range(len(dates))]
    if volumes is None:
        volumes = [1000] * len(dates)
    if stock_name is None:
        stock_name = f"name-{stock_code}"

    rows = []
    for index, raw_date in enumerate(dates):
        normalized_date = pd.Timestamp(raw_date)
        row = {
            "日期": _yyyymmdd(normalized_date),
            "證券代號": stock_code,
            "證券名稱": stock_name,
            "收盤價": close_prices[index],
            "成交股數": volumes[index],
            "oracle_score": score_values[index],
            "IndicatorScore": component_scores[0],
            "PatternScore": component_scores[1],
            "VolumeScore": component_scores[2],
            "BrokerFlowScore": component_scores[3],
            "RevenueScore": component_scores[4],
        }
        if available_dates is not None:
            row["available_date"] = available_dates[index]
        rows.append(row)
    return pd.DataFrame(rows)


def _snapshot_payload(snapshot: RecommendationSnapshotDTO) -> dict:
    return {
        "as_of_date": snapshot.as_of_date,
        "profile_id": snapshot.profile_id,
        "strategy_config": snapshot.strategy_config,
        "regime": snapshot.regime,
        "recommendations": snapshot.recommendations,
        "diagnostics": snapshot.diagnostics,
    }


def test_replay_full_snapshot_is_exact_and_future_append_does_not_change_it():
    dates = list(pd.date_range("2026-08-12", periods=21, freq="D"))
    history = pd.concat(
        [
            _stock_history(
                "A",
                dates,
                stock_name="甲股",
                score_values=[85] * 21,
                component_scores=(10, 20, 30, 40, 50),
                available_dates=[_yyyymmdd(value) for value in dates],
            ),
            _stock_history(
                "B",
                dates,
                stock_name="乙股",
                score_values=[91] * 21,
                component_scores=(11.5, 21.5, 31.5, 41.5, 51.5),
                available_dates=[_yyyymmdd(value) for value in dates],
            ),
        ],
        ignore_index=True,
    )
    future_dates = [pd.Timestamp("2026-09-02"), pd.Timestamp("2026-09-03")]
    future_rows = pd.concat(
        [
            _stock_history(
                code,
                future_dates,
                stock_name=name,
                score_values=[999, 1000],
                component_scores=(999, 999, 999, 999, 999),
                available_dates=[_yyyymmdd(value) for value in future_dates],
            )
            for code, name in (("A", "甲股"), ("B", "乙股"))
        ],
        ignore_index=True,
    )
    config = {
        "regime": "bull",
        "filters": {"price_change_min": "0"},
        "ranking": {"top_n": 2},
        "_portfolio_lookback_days": 80,
    }
    provider, scorer = _configured_provider()
    replay = RecommendationReplayService(provider)

    original = replay.run_snapshot(
        as_of_date="2026-09-01",
        profile_id="profile-r005",
        config=config,
        history=history,
        universe=None,
        top_n=10,
    )
    appended = replay.run_snapshot(
        as_of_date="2026-09-01",
        profile_id="profile-r005",
        config=config,
        history=pd.concat([history, future_rows], ignore_index=True),
        universe=None,
        top_n=10,
    )

    expected = {
        "as_of_date": "2026-09-01",
        "profile_id": "profile-r005",
        "strategy_config": config,
        "regime": "bull",
        "recommendations": [
            {
                "stock_code": "B",
                "stock_name": "乙股",
                "total_score": 91.0,
                "factor_scores": {
                    "technical": 11.5,
                    "pattern": 21.5,
                    "volume": 31.5,
                    "broker_flow": 41.5,
                    "revenue": 51.5,
                },
                "selection_reason": "fixture_reason",
            },
            {
                "stock_code": "A",
                "stock_name": "甲股",
                "total_score": 85.0,
                "factor_scores": {
                    "technical": 10.0,
                    "pattern": 20.0,
                    "volume": 30.0,
                    "broker_flow": 40.0,
                    "revenue": 50.0,
                },
                "selection_reason": "fixture_reason",
            },
        ],
        "diagnostics": [],
    }

    assert _snapshot_payload(original) == expected
    assert _snapshot_payload(appended) == expected
    assert config == expected["strategy_config"]
    assert [frame["日期"].max().strftime("%Y-%m-%d") for frame in scorer.inputs] == [
        "2026-09-01",
        "2026-09-01",
        "2026-09-01",
        "2026-09-01",
    ]


def test_replay_availability_cutoff_excludes_missing_and_future_availability_before_provider():
    dates = list(pd.date_range("2026-08-12", periods=21, freq="D"))
    numeric_dates = [_yyyymmdd(value) for value in dates]
    history_frames = [
        _stock_history(
            "VALID",
            dates,
            score_values=list(range(0, 21)),
            available_dates=numeric_dates,
        ),
        _stock_history(
            "MISSING",
            dates,
            score_values=list(range(100, 121)),
            available_dates=numeric_dates[:-1] + [None],
        ),
        _stock_history(
            "FUTURE",
            dates,
            score_values=list(range(200, 221)),
            available_dates=numeric_dates[:-1] + [20260902],
        ),
    ]
    future_row_date = pd.Timestamp("2026-09-02")
    history_frames.append(
        _stock_history(
            "VALID",
            [future_row_date],
            score_values=[9999],
            available_dates=[_yyyymmdd(future_row_date)],
        )
    )
    history = pd.concat(history_frames, ignore_index=True)
    concrete_provider, scorer = _configured_provider()
    recording_provider = _RecordingProvider(concrete_provider)

    snapshot = RecommendationReplayService(recording_provider).run_snapshot(
        as_of_date="2026-09-01",
        profile_id="availability-profile",
        config={},
        history=history,
        universe=None,
        top_n=10,
    )

    received = recording_provider.calls[0][0]
    received_counts = received.groupby("證券代號").size().to_dict()
    received_latest = received.groupby("證券代號")["日期"].max().dt.strftime("%Y-%m-%d").to_dict()
    observed_recommendations = [
        (item["stock_code"], item["total_score"]) for item in snapshot.recommendations
    ]

    assert received["日期"].max() == pd.Timestamp("2026-09-01")
    assert received_counts == {"FUTURE": 20, "MISSING": 20, "VALID": 21}
    assert received_latest == {
        "FUTURE": "2026-08-31",
        "MISSING": "2026-08-31",
        "VALID": "2026-09-01",
    }
    assert observed_recommendations == [
        ("FUTURE", 219.0),
        ("MISSING", 119.0),
        ("VALID", 20.0),
    ]
    assert snapshot.diagnostics == ["unavailable_rows_excluded:2"]
    assert [str(frame["證券代號"].iloc[0]) for frame in scorer.inputs] == [
        "VALID",
        "MISSING",
        "FUTURE",
    ]


def test_replay_universe_is_a_membership_filter_and_reports_missing_stock_code():
    dates = list(pd.date_range("2026-08-13", periods=20, freq="D"))
    history = pd.concat(
        [
            _stock_history("A", dates, score_values=[70] * 20),
            _stock_history("B", dates, score_values=[70] * 20),
            _stock_history("C", dates, score_values=[99] * 20),
        ],
        ignore_index=True,
    )
    concrete_provider, _ = _configured_provider()
    recording_provider = _RecordingProvider(concrete_provider)
    snapshot = RecommendationReplayService(recording_provider).run_snapshot(
        as_of_date="2026-09-01",
        profile_id="universe-profile",
        config={},
        history=history,
        universe=["B", "A"],
        top_n=10,
    )

    received_codes = recording_provider.calls[0][0]["證券代號"].unique().tolist()
    assert received_codes == ["A", "B"]
    assert [item["stock_code"] for item in snapshot.recommendations] == ["A", "B"]
    assert snapshot.diagnostics == []

    calls: list[pd.DataFrame] = []

    def no_code_provider(data: pd.DataFrame, config: dict, top_n: int) -> list[dict]:
        calls.append(data.copy())
        return []

    missing_code = pd.DataFrame({"日期": [_yyyymmdd(value) for value in dates]})
    missing_code_snapshot = RecommendationReplayService(no_code_provider).run_snapshot(
        as_of_date="2026-09-01",
        profile_id="missing-code-profile",
        config={},
        history=missing_code,
        universe=["A"],
        top_n=10,
    )
    assert len(calls) == 1
    assert missing_code_snapshot.diagnostics == ["missing_stock_code_column"]


def test_dataframe_provider_default_and_configurable_lookback_use_calendar_days():
    latest = pd.Timestamp("2026-09-01")
    recent_dates = list(pd.date_range(end=latest, periods=21, freq="D"))
    default_history = pd.concat(
        [
            _stock_history("LOOKBACK", [latest - pd.Timedelta(days=80)], score_values=[1]),
            _stock_history("LOOKBACK", [latest - pd.Timedelta(days=81)], score_values=[2]),
            _stock_history("LOOKBACK", recent_dates, score_values=[70] * 21),
        ],
        ignore_index=True,
    )
    provider, scorer = _configured_provider()

    default_result = provider(default_history, {}, top_n=5)

    assert len(scorer.inputs) == 1
    default_dates = scorer.inputs[0]["日期"]
    assert len(default_dates) == 22
    assert default_dates.min() == latest - pd.Timedelta(days=80)
    assert latest - pd.Timedelta(days=81) not in set(default_dates)
    assert default_result[0]["total_score"] == 70.0

    custom_days = list(pd.date_range(end=latest, periods=11, freq="D"))
    custom_dates = [value for value in custom_days for _ in range(2)][:21]
    custom_history = pd.concat(
        [
            _stock_history("CUSTOM", [latest - pd.Timedelta(days=11)], score_values=[999]),
            _stock_history("CUSTOM", custom_dates, score_values=[60] * 21),
        ],
        ignore_index=True,
    )
    custom_provider, custom_scorer = _configured_provider()
    custom_result = custom_provider(
        custom_history,
        {"_portfolio_lookback_days": 10},
        top_n=5,
    )

    assert len(custom_scorer.inputs) == 1
    custom_received_dates = custom_scorer.inputs[0]["日期"]
    assert len(custom_received_dates) == 21
    assert custom_received_dates.min() == latest - pd.Timedelta(days=10)
    assert latest - pd.Timedelta(days=11) not in set(custom_received_dates)
    assert custom_result[0]["total_score"] == 60.0


def test_dataframe_provider_default_and_configurable_max_stocks_keep_first_seen_codes():
    dates = list(pd.date_range("2026-08-13", periods=20, freq="D"))
    history = pd.concat(
        [
            _stock_history(f"S{index:03d}", dates, score_values=[10] * 20)
            for index in range(201)
        ],
        ignore_index=True,
    )
    provider, scorer = _configured_provider()

    default_result = provider(history, {}, top_n=250)

    default_seen = [str(frame["證券代號"].iloc[0]) for frame in scorer.inputs]
    assert len(default_seen) == 200
    assert default_seen == [f"S{index:03d}" for index in range(200)]
    assert [item["stock_code"] for item in default_result] == default_seen
    assert "S200" not in {item["stock_code"] for item in default_result}

    custom_result = provider(history, {"_portfolio_max_stocks": 2}, top_n=10)
    custom_seen = [str(frame["證券代號"].iloc[0]) for frame in scorer.inputs[200:]]
    assert custom_seen == ["S000", "S001"]
    assert [item["stock_code"] for item in custom_result] == ["S000", "S001"]


def test_dataframe_provider_volume_fast_filter_has_a_fixed_boundary():
    dates = list(pd.date_range("2026-08-12", periods=21, freq="D"))
    volumes_at_boundary = [1000] * 20 + [1500]
    volumes_below_boundary = [1000] * 20 + [1490]
    history = pd.concat(
        [
            _stock_history(
                "PASS",
                dates,
                score_values=[80] * 21,
                close_prices=[100] * 21,
                volumes=volumes_at_boundary,
            ),
            _stock_history(
                "REJECT",
                dates,
                score_values=[90] * 21,
                close_prices=[100] * 21,
                volumes=volumes_below_boundary,
            ),
        ],
        ignore_index=True,
    )
    provider, scorer = _configured_provider()

    result = provider(
        history,
        {"filters": {"volume_ratio_min": 1.5}},
        top_n=10,
    )

    assert [str(frame["證券代號"].iloc[0]) for frame in scorer.inputs] == ["PASS"]
    assert [item["stock_code"] for item in result] == ["PASS"]
    assert result[0]["total_score"] == 80.0


def test_dataframe_provider_price_change_max_keeps_exact_limit_and_rejects_above():
    dates = list(pd.date_range("2026-08-13", periods=20, freq="D"))
    history = pd.concat(
        [
            _stock_history(
                "AT-LIMIT",
                dates,
                score_values=[80] * 20,
                close_prices=[100] * 19 + [110],
            ),
            _stock_history(
                "ABOVE-LIMIT",
                dates,
                score_values=[99] * 20,
                close_prices=[100] * 19 + [110.01],
            ),
        ],
        ignore_index=True,
    )
    provider, scorer = _configured_provider()

    result = provider(
        history,
        {"filters": {"price_change_max": "10"}},
        top_n=10,
    )

    assert [str(frame["證券代號"].iloc[0]) for frame in scorer.inputs] == ["AT-LIMIT"]
    assert [(item["stock_code"], item["total_score"]) for item in result] == [
        ("AT-LIMIT", 80.0)
    ]


def test_dataframe_provider_preserves_score_fallback_priority_stable_ties_and_top_n():
    dates = list(pd.date_range("2026-08-13", periods=20, freq="D"))
    history = pd.concat(
        [_stock_history(code, dates) for code in ("FINAL", "TOTAL", "COMBINED", "MISSING")],
        ignore_index=True,
    )

    class FallbackScorer:
        def generate_recommendations(self, stock_data: pd.DataFrame, config: dict) -> pd.DataFrame:
            result = stock_data.copy()
            stock_code = str(stock_data["證券代號"].iloc[0])
            if stock_code == "FINAL":
                result["FinalScore"] = 75
                result["TotalScore"] = 99
            elif stock_code == "TOTAL":
                result["TotalScore"] = 75
                result["綜合評分"] = 90
            elif stock_code == "COMBINED":
                result["綜合評分"] = 65
            return result

    provider, _ = _configured_provider(FallbackScorer())
    result = provider(history, {}, top_n=3)

    assert [(item["stock_code"], item["total_score"]) for item in result] == [
        ("FINAL", 75.0),
        ("TOTAL", 75.0),
        ("COMBINED", 65.0),
    ]
    assert [item["stock_code"] for item in provider(history, {}, top_n=4)] == [
        "FINAL",
        "TOTAL",
        "COMBINED",
        "MISSING",
    ]
    assert provider(history, {}, top_n=4)[-1]["total_score"] == 0.0


def test_dataframe_provider_skips_short_history_and_price_filter_rejects_before_scoring():
    short_dates = list(pd.date_range("2026-08-14", periods=19, freq="D"))
    enough_dates = list(pd.date_range("2026-08-12", periods=21, freq="D"))
    short_history = _stock_history("SHORT", short_dates)
    rejected_history = _stock_history(
        "PRICE-REJECT",
        enough_dates,
        close_prices=[100] * 20 + [99],
    )
    provider, scorer = _configured_provider()

    assert provider(short_history, {}, top_n=10) == []
    assert provider(
        rejected_history,
        {"filters": {"price_change_min": "2.0"}},
        top_n=10,
    ) == []
    assert scorer.inputs == []


def test_empty_and_missing_date_history_remain_empty_or_fail_at_the_replay_boundary():
    provider, scorer = _configured_provider()
    empty_history = pd.DataFrame({"日期": [], "證券代號": []})
    assert provider(empty_history, {}, top_n=10) == []

    missing_date_rows = pd.DataFrame({"日期": [None], "證券代號": ["MISSING-DATE"]})
    snapshot = RecommendationReplayService(provider).run_snapshot(
        as_of_date="2026-09-01",
        profile_id="empty-profile",
        config={},
        history=missing_date_rows,
        universe=None,
        top_n=10,
    )
    assert snapshot.as_of_date == "2026-09-01"
    assert snapshot.recommendations == []
    assert snapshot.diagnostics == []
    assert scorer.inputs == []

    with pytest.raises(ValueError, match="history 必須包含 日期 欄位"):
        RecommendationReplayService(provider).run_snapshot(
            as_of_date="2026-09-01",
            profile_id="missing-date-column-profile",
            config={},
            history=pd.DataFrame({"證券代號": ["MISSING-COLUMN"]}),
            universe=None,
            top_n=10,
        )


def test_per_stock_exception_is_silent_and_factor_manifest_only_contains_survivors():
    dates = list(pd.date_range("2026-08-13", periods=20, freq="D"))
    history = pd.concat(
        [
            _stock_history("BROKEN", dates, score_values=[99] * 20),
            _stock_history(
                "SURVIVOR",
                dates,
                score_values=[82.35] * 20,
                component_scores=(1, 2, 70, 4, 5),
            ),
        ],
        ignore_index=True,
    )
    scorer = _ScoreFromFixture(fail_codes={"BROKEN"})
    provider, _ = _configured_provider(scorer)
    snapshot = RecommendationReplayService(provider).run_snapshot(
        as_of_date="2026-09-01",
        profile_id="exception-profile",
        config={},
        history=history,
        universe=None,
        top_n=10,
    )
    manifest = RecommendationPortfolioBacktestService(provider)._build_factor_manifest([snapshot])
    records = manifest["factor_snapshot"]["records"]

    assert [item["stock_code"] for item in snapshot.recommendations] == ["SURVIVOR"]
    assert snapshot.diagnostics == []
    assert {record["stock_code"] for record in records} == {"SURVIVOR"}
    assert [record["factor_name"] for record in records] == [
        "technical.total_score",
        "volume.volume_ratio",
    ]


def test_portfolio_replay_pins_outer_snapshot_dates_and_factor_manifest():
    dates = list(pd.date_range("2026-08-12", periods=21, freq="D"))
    history = _stock_history(
        "2330",
        dates,
        stock_name="台積電",
        score_values=[82.35] * 21,
        component_scores=(70, 60, 70, 50, 40),
        available_dates=[_yyyymmdd(value) for value in dates],
    )
    history = pd.concat(
        [
            history,
            _stock_history(
                "2330",
                [pd.Timestamp("2026-09-02")],
                stock_name="台積電",
                score_values=[9999],
                component_scores=(999, 999, 999, 999, 999),
                available_dates=[20260902],
            ),
        ],
        ignore_index=True,
    )
    provider, scorer = _configured_provider()
    recording_provider = _RecordingProvider(provider)
    config = {"regime": "bull", "_portfolio_lookback_days": 80}

    with pytest.warns(UserWarning, match="同日收盤訊號同日收盤成交"):
        result = RecommendationPortfolioBacktestService(recording_provider).run_portfolio_backtest(
            execution_contract="legacy-same-day-close.v1",
            start_date="2026-09-01",
            end_date="2026-09-02",
            profile_id="portfolio-profile",
            recommendation_config=config,
            history=history,
            initial_capital=100000,
            rebalance_frequency="once",
            top_n=1,
            allocation_method="equal_weight",
            holding_days=1,
        )

    snapshot = result.snapshots[0]
    manifest = result.details["data_manifest"]
    factor_snapshot = manifest["factor_snapshot"]
    factor_contributions = manifest["factor_contributions"]

    assert snapshot.as_of_date == "2026-09-01"
    assert snapshot.profile_id == "portfolio-profile"
    assert snapshot.strategy_config == config
    assert snapshot.regime == "bull"
    assert snapshot.diagnostics == []
    assert snapshot.recommendations == [
        {
            "stock_code": "2330",
            "stock_name": "台積電",
            "total_score": 82.35,
            "factor_scores": {
                "technical": 70.0,
                "pattern": 60.0,
                "volume": 70.0,
                "broker_flow": 50.0,
                "revenue": 40.0,
            },
            "selection_reason": "fixture_reason",
        }
    ]
    assert factor_snapshot == {
        "schema_version": 1,
        "factor_set_version": "factor-layer-v1",
        "decision_date": "2026-09-01",
        "decision_dates": ["2026-09-01"],
        "records": [
            {
                "factor_name": "technical.total_score",
                "stock_code": "2330",
                "as_of_date": "2026-09-01",
                "available_date": "2026-09-01",
                "value": "82.35",
                "score_bp": 8235,
                "quality": "observed",
                "missing_policy": "fail_closed",
                "source_version": "technical-v1",
                "metadata": {},
            },
            {
                "factor_name": "volume.volume_ratio",
                "stock_code": "2330",
                "as_of_date": "2026-09-01",
                "available_date": "2026-09-01",
                "value": "70.0",
                "score_bp": 7000,
                "quality": "observed",
                "missing_policy": "neutral",
                "source_version": "volume-v1",
                "metadata": {"source_field": "factor_scores.volume"},
            },
        ],
        "neutralized": [],
        "skipped": [],
        "diagnostics": [],
    }
    assert factor_contributions == {
        "schema_version": 1,
        "factor_set_version": "factor-layer-v1",
        "by_stock": {
            "2330": [
                {
                    "factor_name": "technical.total_score",
                    "state": "accepted",
                    "score_bp": 8235,
                    "quality": "observed",
                },
                {
                    "factor_name": "volume.volume_ratio",
                    "state": "accepted",
                    "score_bp": 7000,
                    "quality": "observed",
                },
            ]
        },
        "summary_by_factor": {
            "technical.total_score": {
                "accepted_count": 1,
                "neutralized_count": 0,
                "skipped_count": 0,
                "diagnostic_count": 0,
            },
            "volume.volume_ratio": {
                "accepted_count": 1,
                "neutralized_count": 0,
                "skipped_count": 0,
                "diagnostic_count": 0,
            },
        },
    }
    assert recording_provider.calls[0][0]["日期"].max() == pd.Timestamp("2026-09-01")
    assert [frame["日期"].max().strftime("%Y-%m-%d") for frame in scorer.inputs] == [
        "2026-09-01"
    ]


def test_replay_wrapper_preserves_provider_annotation_payload():
    stored_annotation = {
        "probability_bp": 8123,
        "model_version": "historical-model-v1",
        "source": "stored-result",
    }
    stored_recommendation = {
        "stock_code": "2330",
        "stock_name": "台積電",
        "total_score": 82.35,
        "factor_scores": {"technical": 70.0},
        "stored_annotation": stored_annotation,
    }
    def stored_result_provider(data: pd.DataFrame, config: dict, top_n: int) -> list[dict]:
        return [deepcopy(stored_recommendation)]

    dates = list(pd.date_range("2026-08-13", periods=20, freq="D"))
    history = _stock_history("2330", dates)
    snapshot = RecommendationReplayService(stored_result_provider).run_snapshot(
        as_of_date="2026-09-01",
        profile_id="stored-profile",
        config={},
        history=history,
        universe=None,
        top_n=1,
    )

    assert snapshot.recommendations == [stored_recommendation]
    assert snapshot.recommendations[0]["stored_annotation"] == stored_annotation
