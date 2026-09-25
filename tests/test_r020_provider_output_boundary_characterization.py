from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import pytest

from app_module.recommendation_dataframe_provider import RecommendationDataFrameProvider
from app_module.recommendation_replay_service import RecommendationReplayService


def _history(codes: tuple[str, ...]) -> pd.DataFrame:
    dates = pd.date_range("2026-09-01", periods=20, freq="D")
    rows: list[dict[str, Any]] = []
    for code in codes:
        for index, day in enumerate(dates):
            rows.append(
                {
                    "日期": int(day.strftime("%Y%m%d")),
                    "證券代號": code,
                    "證券名稱": f"name-{code}",
                    "收盤價": 100 + index,
                    "成交股數": 1_000 + index,
                }
            )
    return pd.DataFrame(rows)


class _MappedScorer:
    def __init__(self, rows: Mapping[str, Mapping[str, Any]], *, failures: set[str] | None = None):
        self.rows = rows
        self.failures = failures or set()
        self.calls: list[str] = []

    def generate_recommendations(self, stock_data: pd.DataFrame, config: dict) -> pd.DataFrame:
        code = str(stock_data["證券代號"].iloc[0])
        self.calls.append(code)
        if code in self.failures:
            raise RuntimeError(f"synthetic scorer failure: {code}")

        result = stock_data.copy()
        for column, value in self.rows.get(code, {}).items():
            # 保留明確的 None/pd.NA；pandas 推斷成 float dtype 時可能將 None
            # 靜默轉成 NaN，掩蓋舊邏輯的 truthiness 邊界。
            values = pd.Series([None] * len(result), index=result.index, dtype=object)
            values.iloc[-1] = value
            result[column] = values
        return result


class _RecordingReasonEngine:
    def __init__(self) -> None:
        self.generated: list[tuple[str, dict[str, Any]]] = []
        self.formatted: list[tuple[str, list[str], int]] = []

    def generate_reasons(self, latest_row: pd.Series, config: dict) -> list[str]:
        code = str(latest_row["證券代號"])
        self.generated.append((code, latest_row.to_dict()))
        return ["r1", "r2", "r3", "r4"]

    def format_reason_text(self, reasons: list[str], max_reasons: int = 3) -> str:
        current_code = self.generated[-1][0]
        self.formatted.append((current_code, list(reasons), max_reasons))
        return ",".join(reasons[:max_reasons])


def _provider(
    rows: Mapping[str, Mapping[str, Any]], *, failures: set[str] | None = None
) -> tuple[RecommendationDataFrameProvider, _MappedScorer, _RecordingReasonEngine]:
    provider = RecommendationDataFrameProvider()
    scorer = _MappedScorer(rows, failures=failures)
    reason_engine = _RecordingReasonEngine()
    provider.strategy_configurator = scorer
    provider.reason_engine = reason_engine
    return provider, scorer, reason_engine


def test_provider_score_presence_truthiness_and_post_scorer_skip_boundary():
    history = _history(
        (
            "ZERO",
            "NULL",
            "MISSING",
            "NAN",
            "BAD-SCORE",
            "BAD-FACTOR",
            "SCORER-ERROR",
            "SURVIVOR",
        )
    )
    provider, scorer, reasons = _provider(
        {
            "ZERO": {"FinalScore": 0.0, "TotalScore": 99.0},
            "NULL": {"FinalScore": None, "TotalScore": 88.0},
            "MISSING": {"TotalScore": 77.0},
            "NAN": {"FinalScore": np.nan},
            "BAD-SCORE": {"FinalScore": pd.NA},
            "BAD-FACTOR": {"FinalScore": 61.0, "IndicatorScore": pd.NA},
            "SURVIVOR": {
                "FinalScore": 80.0,
                "IndicatorScore": 0,
                "PatternScore": None,
                "VolumeScore": np.nan,
                "BrokerFlowScore": 4,
            },
        },
        failures={"SCORER-ERROR"},
    )

    result = provider(history, {}, top_n=20)
    by_code = {item["stock_code"]: item for item in result}

    # 先選取存在但為 falsey 的 FinalScore，再套用 `or 0`；存在的 None
    # 不會回退到 TotalScore，只有鍵不存在時才會回退。
    assert by_code["ZERO"]["total_score"] == 0.0
    assert by_code["NULL"]["total_score"] == 0.0
    assert by_code["MISSING"]["total_score"] == 77.0
    assert np.isnan(by_code["NAN"]["total_score"])

    # row projection 的 pd.NA truthiness／轉換錯誤與 scoring 共用 per-stock try，
    # 因此該股票會被靜默略過，其他列仍保留。
    assert "BAD-SCORE" not in by_code
    assert "BAD-FACTOR" not in by_code
    assert "SCORER-ERROR" not in by_code
    factor_scores = by_code["SURVIVOR"]["factor_scores"]
    assert factor_scores["technical"] == 0.0
    assert factor_scores["pattern"] == 0.0
    assert factor_scores["broker_flow"] == 4.0
    assert factor_scores["revenue"] == 0.0
    # NaN 不等於自身，因此明確單獨檢查此 factor。
    assert np.isnan(factor_scores["volume"])
    assert by_code["SURVIVOR"]["selection_reason"] == "r1,r2,r3"

    generated_codes = [code for code, _ in reasons.generated]
    formatted_codes = [code for code, _, _ in reasons.formatted]
    assert generated_codes == [
        "ZERO",
        "NULL",
        "MISSING",
        "NAN",
        "BAD-SCORE",
        "BAD-FACTOR",
        "SURVIVOR",
    ]
    # 格式化是輸出組裝的最後一步；轉換失敗時不會執行格式化。
    assert formatted_codes == ["ZERO", "NULL", "MISSING", "NAN", "SURVIVOR"]
    assert all(max_reasons == 3 for _, _, max_reasons in reasons.formatted)
    assert scorer.calls == [
        "ZERO",
        "NULL",
        "MISSING",
        "NAN",
        "BAD-SCORE",
        "BAD-FACTOR",
        "SCORER-ERROR",
        "SURVIVOR",
    ]


def test_provider_uses_python_descending_sort_for_nan_and_infinities():
    codes = ("NAN", "POS-INF", "TEN", "NEG-INF", "TWENTY")
    provider, _, _ = _provider(
        {
            "NAN": {"FinalScore": np.nan},
            "POS-INF": {"FinalScore": np.inf},
            "TEN": {"FinalScore": 10.0},
            "NEG-INF": {"FinalScore": -np.inf},
            "TWENTY": {"FinalScore": 20.0},
        }
    )

    result = provider(_history(codes), {}, top_n=len(codes))

    # 這是舊版對 Python float key 執行穩定 `list.sort(reverse=True)` 的實際結果。
    # NaN 不構成一般的全序關係。
    assert [item["stock_code"] for item in result] == [
        "NAN",
        "POS-INF",
        "TWENTY",
        "TEN",
        "NEG-INF",
    ]
    assert np.isnan(result[0]["total_score"])
    assert result[1]["total_score"] == np.inf
    assert result[-1]["total_score"] == -np.inf


@pytest.mark.parametrize(
    ("top_n", "expected"),
    [
        (0, []),
        (-1, ["A", "B"]),
        (-4, []),
    ],
)
def test_provider_preserves_zero_and_negative_python_slice_top_n(top_n: int, expected: list[str]):
    codes = ("A", "B", "C")
    provider, _, _ = _provider(
        {
            "A": {"FinalScore": 3.0},
            "B": {"FinalScore": 2.0},
            "C": {"FinalScore": 1.0},
        }
    )

    result = provider(_history(codes), {}, top_n=top_n)

    assert [item["stock_code"] for item in result] == expected


def test_snapshot_preserves_provider_then_snapshot_negative_and_zero_top_n_slices():
    codes = ("A", "B", "C", "D", "E")

    class CapturingProvider(RecommendationDataFrameProvider):
        def __init__(self) -> None:
            super().__init__()
            self.strategy_configurator = _MappedScorer(
                {
                    code: {"FinalScore": 5 - index}
                    for index, code in enumerate(codes)
                }
            )
            self.reason_engine = _RecordingReasonEngine()
            self.provider_outputs: list[list[dict[str, Any]]] = []

        def run_with_as_of(
            self,
            as_of_data: pd.DataFrame,
            config: dict[str, Any],
            top_n: int,
            as_of_date: date,
        ) -> list[dict[str, Any]]:
            rows = super().run_with_as_of(as_of_data, config, top_n, as_of_date)
            self.provider_outputs.append(rows)
            return rows

    provider = CapturingProvider()
    service = RecommendationReplayService(provider)
    history = _history(codes)

    negative = service.run_snapshot(
        as_of_date="2026-09-20",
        profile_id="synthetic-negative-top-n",
        config={},
        history=history,
        universe=None,
        top_n=-1,
    )

    # Provider 先套用第一次 Python 切片（5 -> 4）；snapshot wrapper 再對
    # 實際取得的 provider 列套用第二次切片（4 -> 3）。
    assert len(provider.provider_outputs[-1]) == 4
    assert [item["stock_code"] for item in provider.provider_outputs[-1]] == [
        "A",
        "B",
        "C",
        "D",
    ]
    assert [item["stock_code"] for item in negative.recommendations] == [
        "A",
        "B",
        "C",
    ]

    assert negative.canonical_execution is None
    negative_wire = asdict(negative)
    assert set(negative_wire) == {
        "as_of_date",
        "profile_id",
        "strategy_config",
        "regime",
        "recommendations",
        "diagnostics",
    }

    zero = service.run_snapshot(
        as_of_date="2026-09-20",
        profile_id="synthetic-zero-top-n",
        config={},
        history=history,
        universe=None,
        top_n=0,
    )

    assert provider.provider_outputs[-1] == []
    assert zero.recommendations == []
    assert zero.canonical_execution is None
    assert set(asdict(zero)) == set(negative_wire)
