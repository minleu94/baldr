"""固定 replay 選股上限、可得時間與歷史列數的同次 caller 行為。"""

from __future__ import annotations

from datetime import date
from typing import Any, cast

import pandas as pd

from app_module.recommendation_dataframe_provider import RecommendationDataFrameProvider
from app_module.recommendation_portfolio_dtos import RecommendationSnapshotDTO
from app_module.recommendation_replay_service import RecommendationReplayService


class _SelectionScorer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def generate_recommendations(
        self, stock_data: pd.DataFrame, _config: dict[str, object]
    ) -> pd.DataFrame:
        stock_code = str(stock_data["證券代號"].iloc[0])
        scorer_dates = tuple(
            pd.to_datetime(stock_data["日期"]).dt.strftime("%Y-%m-%d").tolist()
        )
        self.calls.append((stock_code, scorer_dates))

        result = stock_data.copy(deep=True)
        result["FinalScore"] = {"A": 80.0, "B": 90.0}[stock_code]
        result["IndicatorScore"] = 11.0
        result["PatternScore"] = 22.0
        result["VolumeScore"] = 33.0
        result["BrokerFlowScore"] = 44.0
        result["RevenueScore"] = 55.0
        return result


class _SelectionReasonEngine:
    def generate_reasons(
        self, latest_row: pd.Series, _config: dict[str, object]
    ) -> list[str]:
        return [f"固定原因-{latest_row['證券代號']}"]

    def format_reason_text(self, reasons: list[str], max_reasons: int = 3) -> str:
        return "|".join(reasons[:max_reasons])


def _history() -> tuple[pd.DataFrame, dict[str, tuple[str, ...]]]:
    as_of = pd.Timestamp("2026-09-24")
    recent_days = list(pd.date_range("2026-09-04", as_of, freq="D"))
    p19_days = recent_days[:-1]
    older_a = [pd.Timestamp("2026-08-20"), pd.Timestamp("2026-09-03")]
    older_b = [pd.Timestamp("2026-08-19"), pd.Timestamp("2026-09-02")]
    rows: list[dict[str, object]] = []

    def add_rows(
        code: str,
        days: list[pd.Timestamp],
        *,
        missing_availability_day: pd.Timestamp | None = None,
        future_availability_day: pd.Timestamp | None = None,
    ) -> None:
        for index, day in enumerate(days):
            available_date: object = int(day.strftime("%Y%m%d"))
            if day == missing_availability_day:
                available_date = None
            elif day == future_availability_day:
                available_date = 20260925
            rows.append(
                {
                    "日期": int(day.strftime("%Y%m%d")),
                    "available_date": available_date,
                    "證券代號": code,
                    "證券名稱": f"名稱-{code}",
                    "收盤價": 100 + index,
                    "成交股數": 1_000 + index,
                }
            )

    # 原始列的 first-seen 順序是 P19、A、B、C；P19 在 max_stocks 截取前佔名額。
    add_rows(
        "P19",
        p19_days,
        missing_availability_day=pd.Timestamp("2026-09-10"),
    )
    add_rows(
        "A",
        older_a + recent_days,
        future_availability_day=pd.Timestamp("2026-09-11"),
    )
    add_rows("B", older_b + recent_days)
    add_rows("C", recent_days + [pd.Timestamp("2026-09-25")])

    expected_recent_a = tuple(
        day.strftime("%Y-%m-%d")
        for day in recent_days
        if day != pd.Timestamp("2026-09-11")
    )
    expected_unbounded_a = tuple(
        day.strftime("%Y-%m-%d")
        for day in older_a + recent_days
        if day != pd.Timestamp("2026-09-11")
    )
    expected_unbounded_b = tuple(
        day.strftime("%Y-%m-%d") for day in older_b + recent_days
    )
    expected_recent_b = tuple(day.strftime("%Y-%m-%d") for day in recent_days)
    return pd.DataFrame(rows), {
        "recent_a": expected_recent_a,
        "recent_b": expected_recent_b,
        "unbounded_a": expected_unbounded_a,
        "unbounded_b": expected_unbounded_b,
    }


def _run_snapshot(
    history: pd.DataFrame,
    *,
    config: dict[str, object],
    parent_result_id: str,
) -> tuple[RecommendationSnapshotDTO, _SelectionScorer]:
    provider = RecommendationDataFrameProvider()
    scorer = _SelectionScorer()
    provider.strategy_configurator = cast(Any, scorer)
    provider.reason_engine = cast(Any, _SelectionReasonEngine())
    snapshot = RecommendationReplayService(provider).run_snapshot(
        as_of_date="2026-09-24",
        profile_id="r020-selection-cutoff-fixed-vector",
        config=config,
        history=history,
        universe=None,
        top_n=10,
        parent_result_id=parent_result_id,
    )
    return snapshot, scorer


def test_signed_selection_limits_and_cutoff_share_one_replay_call() -> None:
    """以 R005 固定順序檢查 service cutoff→provider slice→history gate。"""

    history, expected_dates = _history()
    assert len(expected_dates["recent_a"]) == 20
    assert len(expected_dates["recent_b"]) == 21

    # 正 lookback 保留 9/4 起的 21 個曆日。P19 的一列缺 available_date，
    # 所以它只有 19 列；但 first-seen cap 在 history gate 前套用，A/B 的前兩席被 P19、A 佔用。
    limited_snapshot, limited_scorer = _run_snapshot(
        history,
        config={"_portfolio_lookback_days": 20, "_portfolio_max_stocks": 2},
        parent_result_id="parent-r020-selection-limited",
    )

    assert limited_scorer.calls == [("A", expected_dates["recent_a"])]
    assert limited_snapshot.as_of_date == "2026-09-24"
    assert limited_snapshot.diagnostics == ["unavailable_rows_excluded:2"]
    assert limited_snapshot.recommendations == [
        {
            "stock_code": "A",
            "stock_name": "名稱-A",
            "total_score": 80.0,
            "factor_scores": {
                "technical": 11.0,
                "pattern": 22.0,
                "volume": 33.0,
                "broker_flow": 44.0,
                "revenue": 55.0,
            },
            "selection_reason": "固定原因-A",
        }
    ]
    assert limited_snapshot.canonical_execution is None

    # 同一 positive lookback 下放寬一席，明確證明 21-row B 通過；
    # 這與 max=2 例共同固定 first-seen 上限是在 history gate 前套用。
    boundary_snapshot, boundary_scorer = _run_snapshot(
        history,
        config={"_portfolio_lookback_days": 20, "_portfolio_max_stocks": 3},
        parent_result_id="parent-r020-selection-boundary",
    )
    assert boundary_scorer.calls == [
        ("A", expected_dates["recent_a"]),
        ("B", expected_dates["recent_b"]),
    ]
    assert [row["stock_code"] for row in boundary_snapshot.recommendations] == [
        "B",
        "A",
    ]
    assert [row["total_score"] for row in boundary_snapshot.recommendations] == [
        90.0,
        80.0,
    ]
    assert boundary_snapshot.canonical_execution is None

    # 負 lookback 沿舊規則不裁日期；max_stocks=-1 保留 Python 的 unique()[:-1]。
    # P19 仍先佔 first-seen 名額後被 19-row gate 略過；末位 C（含 cutoff 後資料）不進 scorer。
    signed_snapshot, signed_scorer = _run_snapshot(
        history,
        config={"_portfolio_lookback_days": -5, "_portfolio_max_stocks": -1},
        parent_result_id="parent-r020-selection-signed",
    )

    assert signed_scorer.calls == [
        ("A", expected_dates["unbounded_a"]),
        ("B", expected_dates["unbounded_b"]),
    ]
    assert signed_snapshot.as_of_date == "2026-09-24"
    assert signed_snapshot.diagnostics == ["unavailable_rows_excluded:2"]
    assert signed_snapshot.recommendations == [
        {
            "stock_code": "B",
            "stock_name": "名稱-B",
            "total_score": 90.0,
            "factor_scores": {
                "technical": 11.0,
                "pattern": 22.0,
                "volume": 33.0,
                "broker_flow": 44.0,
                "revenue": 55.0,
            },
            "selection_reason": "固定原因-B",
        },
        {
            "stock_code": "A",
            "stock_name": "名稱-A",
            "total_score": 80.0,
            "factor_scores": {
                "technical": 11.0,
                "pattern": 22.0,
                "volume": 33.0,
                "broker_flow": 44.0,
                "revenue": 55.0,
            },
            "selection_reason": "固定原因-A",
        },
    ]
    assert signed_snapshot.canonical_execution is None
