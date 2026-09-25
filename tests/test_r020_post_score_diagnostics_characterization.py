from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import pytest

import decision_module.strategy_configurator as strategy_module
from app_module.recommendation_dataframe_provider import (
    RecommendationDataFrameProvider,
    ReplayProviderCallResultV1,
)
from decision_module.recommendation.evaluate import (
    RecommendationEvaluator,
    ReplayCandidateScoringOutcomeV1,
    ReplayScorerDispositionV1,
    ReplayScorerResponseV1,
)
from decision_module.strategy_configurator import StrategyConfigurator


def _screen_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "證券代號": ["SYN"],
            "漲幅%": [0.0],
            "成交量變化率%": [20.0],
            "RSI": [50],
        }
    )


def _history(row_count: int = 21, stock_code: str = "SYN") -> pd.DataFrame:
    dates = pd.date_range("2026-09-01", periods=row_count, freq="D")
    return pd.DataFrame(
        {
            "日期": [int(value.strftime("%Y%m%d")) for value in dates],
            "證券代號": [stock_code] * row_count,
            "證券名稱": [f"名稱-{stock_code}"] * row_count,
            "開盤價": [100] * row_count,
            "最高價": [101] * row_count,
            "最低價": [99] * row_count,
            "收盤價": [100] * row_count,
            "成交股數": [1000] * row_count,
            "RSI": [50] * row_count,
        }
    )


def _capture_terminals(
    monkeypatch: pytest.MonkeyPatch,
) -> list[ReplayCandidateScoringOutcomeV1]:
    terminals: list[ReplayCandidateScoringOutcomeV1] = []
    original = RecommendationEvaluator.complete_replay_scoring

    def observe(
        evaluator: RecommendationEvaluator,
        step: Any,
        response: ReplayScorerResponseV1,
    ) -> ReplayCandidateScoringOutcomeV1:
        terminal = original(evaluator, step, response)
        terminals.append(terminal)
        return terminal

    monkeypatch.setattr(RecommendationEvaluator, "complete_replay_scoring", observe)
    return terminals


def _run_provider(
    monkeypatch: pytest.MonkeyPatch,
    *,
    filters: dict[str, Any] | None = None,
    stock_code: str = "SYN",
) -> tuple[ReplayProviderCallResultV1, list[ReplayCandidateScoringOutcomeV1]]:
    provider = RecommendationDataFrameProvider()
    terminals = _capture_terminals(monkeypatch)
    config: dict[str, Any] = {} if filters is None else {"filters": filters}
    result = provider.run_with_as_of_handoff(
        _history(stock_code=stock_code),
        config,
        top_n=10,
        as_of_date=date(2026, 9, 21),
    )
    return result, terminals


def test_diagnostic_price_warning_and_counter_precede_empty_volume_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[tuple[int, dict[str, Any]]] = []
    original = strategy_module.filter_completed_frame

    def observe(frame: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
        calls.append((len(frame), dict(filters)))
        return original(frame, filters)

    monkeypatch.setattr(strategy_module, "filter_completed_frame", observe)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_volume_filter_log_count", 0, raising=False)
    caplog.set_level("WARNING", logger="decision_module.strategy_configurator")

    with pytest.raises(TypeError, match="Invalid comparison between dtype=float64 and str"):
        StrategyConfigurator().screen_stocks(
            _screen_frame(),
            {"price_change_min": 100, "volume_ratio_min": "bad"},
        )

    assert calls == [
        (1, {"price_change_min": 100}),
        (0, {"volume_ratio_min": "bad"}),
    ]
    assert [record.message for record in caplog.records if record.levelname == "WARNING"] == [
        "[漲幅篩選] 要求 >= 100%, 但樣本值=0.00%"
    ]
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 1
    assert getattr(StrategyConfigurator, "_volume_filter_log_count") == 0


def test_price_min_empty_then_invalid_max_fails_inside_diagnostic_pass(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[tuple[int, dict[str, Any]]] = []
    original = strategy_module.filter_completed_frame

    def observe(frame: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
        calls.append((len(frame), dict(filters)))
        return original(frame, filters)

    monkeypatch.setattr(strategy_module, "filter_completed_frame", observe)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    caplog.set_level("WARNING", logger="decision_module.strategy_configurator")

    with pytest.raises(TypeError, match="Invalid comparison between dtype=float64 and str"):
        StrategyConfigurator().screen_stocks(
            _screen_frame(),
            {
                "price_change_min": 100,
                "price_change_max": "bad",
                "volume_ratio_min": "bad",
            },
        )

    assert calls == [
        (1, {"price_change_min": 100, "price_change_max": "bad"}),
    ]
    assert not [record for record in caplog.records if record.levelname == "WARNING"]
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 0


def test_diagnostic_warning_precedes_final_empty_rsi_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[tuple[int, dict[str, Any]]] = []
    original = strategy_module.filter_completed_frame

    def observe(frame: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
        calls.append((len(frame), dict(filters)))
        return original(frame, filters)

    monkeypatch.setattr(strategy_module, "filter_completed_frame", observe)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    caplog.set_level("WARNING", logger="decision_module.strategy_configurator")

    with pytest.raises(TypeError, match="Invalid comparison between dtype=int64 and str"):
        StrategyConfigurator().screen_stocks(
            _screen_frame(),
            {"price_change_min": 100, "rsi_min": "bad"},
        )

    assert calls == [
        (1, {"price_change_min": 100}),
        (1, {"price_change_min": 100, "rsi_min": "bad"}),
    ]
    assert [record.message for record in caplog.records if record.levelname == "WARNING"] == [
        "[漲幅篩選] 要求 >= 100%, 但樣本值=0.00%"
    ]
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 1


def test_missing_fields_absent_keys_and_present_none_keep_native_behavior(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configurator = StrategyConfigurator()
    caplog.set_level("WARNING", logger="decision_module.strategy_configurator")
    missing = pd.DataFrame({"證券代號": ["MISSING"]})
    assert configurator.screen_stocks(
        missing,
        {
            "price_change_min": "bad",
            "volume_ratio_min": "bad",
            "rsi_min": "bad",
        },
    )["證券代號"].tolist() == ["MISSING"]

    frame = _screen_frame()
    assert configurator.screen_stocks(frame, {})["證券代號"].tolist() == ["SYN"]
    # 欄位存在但門檻值為 None 時，legacy pandas comparison 會排除該列，並走價格診斷。
    assert configurator.screen_stocks(frame, {"price_change_min": None}).empty
    assert caplog.records[-1].message == "[漲幅篩選] 要求 >= None%, 但樣本值=0.00%"


def test_rsi_column_precedence_is_rsi_then_lowercase_then_rsi_14() -> None:
    both = pd.DataFrame(
        {"證券代號": ["A"], "RSI": [40], "rsi": [70], "RSI_14": [90]}
    )
    assert StrategyConfigurator().screen_stocks(both, {"rsi_min": 60}).empty

    lowercase_first = pd.DataFrame(
        {"證券代號": ["B"], "rsi": [70], "RSI_14": [40]}
    )
    assert StrategyConfigurator().screen_stocks(
        lowercase_first, {"rsi_min": 60}
    )["證券代號"].tolist() == ["B"]

    fallback = pd.DataFrame({"證券代號": ["C"], "RSI_14": [70]})
    assert StrategyConfigurator().screen_stocks(
        fallback, {"rsi_min": 60}
    )["證券代號"].tolist() == ["C"]


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("price_change_min", ["ZERO", "POS_INF", "GT"]),
        ("price_change_max", ["NEG_INF", "ZERO"]),
    ],
)
def test_real_numeric_inclusive_comparisons_keep_nan_and_infinity_semantics(
    key: str,
    expected: list[str],
) -> None:
    frame = pd.DataFrame(
        {
            "證券代號": ["NAN", "NEG_INF", "ZERO", "POS_INF", "GT"],
            "漲幅%": [np.nan, -np.inf, 0.0, np.inf, 2.0],
        }
    )
    filters = {key: 0.0}
    assert StrategyConfigurator().screen_stocks(frame, filters)["證券代號"].tolist() == expected


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("price_change_min", ["EQUAL", "IMAG_GT", "REAL_GT"]),
        ("price_change_max", ["EQUAL", "IMAG_LT"]),
    ],
)
def test_numpy_complex_inclusive_comparisons_follow_current_native_profile(
    key: str,
    expected: list[str],
) -> None:
    frame = pd.DataFrame(
        {
            "證券代號": ["EQUAL", "IMAG_LT", "IMAG_GT", "REAL_GT"],
            "漲幅%": np.asarray([1 + 1j, 1 + 0j, 1 + 2j, 2 + 0j], dtype=np.complex128),
        }
    )
    threshold = np.complex128(1 + 1j)
    assert StrategyConfigurator().screen_stocks(
        frame, {key: threshold}
    )["證券代號"].tolist() == expected


@pytest.mark.parametrize(
    ("key", "operator"),
    [("price_change_min", ">="), ("price_change_max", "<=")],
)
def test_python_complex_object_comparison_raises_native_typeerror(
    key: str,
    operator: str,
) -> None:
    frame = pd.DataFrame(
        {"證券代號": ["PY_COMPLEX"], "漲幅%": pd.Series([complex(1, 1)], dtype=object)}
    )
    with pytest.raises(TypeError, match=operator):
        StrategyConfigurator().screen_stocks(frame, {key: complex(1, 0)})


def test_concrete_provider_preserves_scorer_empty_and_post_filter_exception_terminals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # StrategyConfigurator 受保護的打分區塊會把一般錯誤轉成空 DataFrame；
    # concrete replay provider 因而記錄 SKIPPED_EMPTY。
    provider = RecommendationDataFrameProvider()
    terminals = _capture_terminals(monkeypatch)

    def scoring_error(*args: Any, **kwargs: Any) -> pd.DataFrame:
        raise RuntimeError("synthetic scorer failure")

    monkeypatch.setattr(provider.strategy_configurator.scoring_engine, "calculate_total_score", scoring_error)
    empty_after_score = provider.run_with_as_of_handoff(
        _history(stock_code="SCORER_ERROR"), {}, 10, date(2026, 9, 21)
    )
    assert empty_after_score.rows == []
    assert empty_after_score.scoring_outcomes == ()
    assert terminals[-1].request.stock_code == "SCORER_ERROR"
    assert terminals[-1].response.disposition is ReplayScorerDispositionV1.SKIPPED_EMPTY

    # 打分後 RSI 比較位於該保護區塊之外，會進入 provider 的逐檔例外終端。
    provider_after_filter = RecommendationDataFrameProvider()
    post_filter_error = provider_after_filter.run_with_as_of_handoff(
        _history(stock_code="FILTER_ERROR"),
        {"filters": {"rsi_min": "bad"}},
        10,
        date(2026, 9, 21),
    )
    assert post_filter_error.rows == []
    assert post_filter_error.scoring_outcomes == ()
    assert terminals[-1].request.stock_code == "FILTER_ERROR"
    assert terminals[-1].response.disposition is ReplayScorerDispositionV1.SKIPPED_SCORER_EXCEPTION
    assert terminals[-1].response.error_type == "TypeError"


def test_concrete_provider_keeps_visible_v1_row_and_two_filter_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, terminals = _run_provider(monkeypatch, stock_code="VISIBLE")
    assert result.rows == [
        {
            "stock_code": "VISIBLE",
            "stock_name": "名稱-VISIBLE",
            "total_score": 50.0,
            "factor_scores": {
                "technical": 50.0,
                "pattern": 50.0,
                "volume": 50.0,
                "broker_flow": 0.0,
                "revenue": 0.0,
            },
            "selection_reason": "符合策略條件",
        }
    ]
    assert len(result.scoring_outcomes) == 1
    outcome = result.scoring_outcomes[0]
    assert outcome is not None
    assert outcome.response.disposition is ReplayScorerDispositionV1.SCORED
    filter_outcomes = outcome.assessment.filter_outcomes
    assert filter_outcomes is not None
    assert set(filter_outcomes) == {"replay_prefilter", "replay_scoring"}
    assert terminals[-1].response.disposition is ReplayScorerDispositionV1.SCORED


def test_concrete_provider_turns_post_score_rejection_into_existing_empty_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, terminals = _run_provider(
        monkeypatch,
        filters={"rsi_min": 51},
        stock_code="FILTERED",
    )
    assert result.rows == []
    assert result.scoring_outcomes == ()
    assert terminals[-1].request.stock_code == "FILTERED"
    assert terminals[-1].response.disposition is ReplayScorerDispositionV1.SKIPPED_EMPTY
    assert terminals[-1].response.reason_code == "scorer_empty_result"
