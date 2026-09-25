"""以手算帳本固定 concrete provider 的組合回測端到端結果。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from backtest_module.broker_simulator import NEXT_OPEN_CONTRACT
from app_module.recommendation_dataframe_provider import RecommendationDataFrameProvider
from app_module.recommendation_portfolio_backtest_service import (
    RecommendationPortfolioBacktestService,
)
from app_module.recommendation_replay_service import RecommendationReplayService


class _GoldenScorer:
    """依合成列給分；第二個 rebalance 日明示空結果與 scorer 錯誤。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate_recommendations(
        self, stock_data: pd.DataFrame, config: dict
    ) -> pd.DataFrame:
        stock_code = str(stock_data["證券代號"].iloc[0])
        latest_date = pd.Timestamp(stock_data["日期"].max()).strftime("%Y-%m-%d")
        self.calls.append((stock_code, latest_date))

        if latest_date == "2026-01-12" and stock_code == "A":
            return stock_data.iloc[0:0].copy()
        if latest_date == "2026-01-12" and stock_code == "B":
            raise RuntimeError("synthetic scorer failure on second snapshot")

        result = stock_data.copy()
        result["FinalScore"] = pd.to_numeric(result["oracle_score"], errors="raise")
        return result


class _GoldenReasonEngine:
    def generate_reasons(self, latest_row: pd.Series, config: dict) -> list[str]:
        return ["fixture_reason"]

    def format_reason_text(self, reasons: list[str], max_reasons: int = 3) -> str:
        return "|".join(reasons[:max_reasons])


def _history() -> pd.DataFrame:
    """建 20 個前置交易日及持有期資料；不讀本機或正式行情。"""

    dates = pd.bdate_range(start="2025-12-10", end="2026-01-13")
    special_prices = {
        "A": {
            pd.Timestamp("2026-01-06"): 100,
            pd.Timestamp("2026-01-07"): 105,
            pd.Timestamp("2026-01-08"): 110,
        },
        "B": {
            pd.Timestamp("2026-01-06"): 200,
            pd.Timestamp("2026-01-07"): 190,
            pd.Timestamp("2026-01-08"): 180,
        },
    }
    candidates = {
        "A": ("Alpha", 90, (70, 60, 50, 40, 30), 100),
        "B": ("Beta", 80, (65, 55, 45, 35, 25), 200),
    }
    rows: list[dict[str, object]] = []
    for code, (name, score, factors, base_price) in candidates.items():
        for timestamp in dates:
            close = special_prices[code].get(timestamp, base_price)
            rows.append(
                {
                    "日期": int(timestamp.strftime("%Y%m%d")),
                    "證券代號": code,
                    "證券名稱": name,
                    "收盤價": close,
                    "成交股數": 1000,
                    "oracle_score": score,
                    "IndicatorScore": factors[0],
                    "PatternScore": factors[1],
                    "VolumeScore": factors[2],
                    "BrokerFlowScore": factors[3],
                    "RevenueScore": factors[4],
                }
            )
    return pd.DataFrame(rows)


def test_concrete_provider_portfolio_golden_with_empty_and_error_rebalance_day():
    history = _history()
    parsed_dates = pd.to_datetime(history["日期"], format="%Y%m%d")
    for stock_code in ("A", "B"):
        stock_mask = history["證券代號"] == stock_code
        assert int((parsed_dates[stock_mask] <= pd.Timestamp("2026-01-06")).sum()) == 20

    scorer = _GoldenScorer()
    provider = RecommendationDataFrameProvider()
    provider.strategy_configurator = scorer
    provider.reason_engine = _GoldenReasonEngine()

    with pytest.warns(UserWarning, match="同日收盤訊號同日收盤成交"):
        result = RecommendationPortfolioBacktestService(provider).run_portfolio_backtest(
            start_date="2026-01-06",
            end_date="2026-01-13",
            profile_id="r020-hand-calculated-golden",
            recommendation_config={"regime": "Trend"},
            history=history,
            initial_capital=1_000_000,
            rebalance_frequency="weekly",
            top_n=2,
            allocation_method="equal_weight",
            holding_days=2,
            execution_contract="legacy-same-day-close.v1",
        )

    # R005 v1 row oracle：兩檔在第一個 cutoff 依 FinalScore 排序；第二個 cutoff
    # 一檔 scorer 回空、一檔 scorer 拋錯，兩者都不成為推薦或投資標的。
    expected_rows = [
        {
            "stock_code": "A",
            "stock_name": "Alpha",
            "total_score": 90.0,
            "factor_scores": {
                "technical": 70.0,
                "pattern": 60.0,
                "volume": 50.0,
                "broker_flow": 40.0,
                "revenue": 30.0,
            },
            "selection_reason": "fixture_reason",
        },
        {
            "stock_code": "B",
            "stock_name": "Beta",
            "total_score": 80.0,
            "factor_scores": {
                "technical": 65.0,
                "pattern": 55.0,
                "volume": 45.0,
                "broker_flow": 35.0,
                "revenue": 25.0,
            },
            "selection_reason": "fixture_reason",
        },
    ]
    assert scorer.calls == [
        ("A", "2026-01-06"),
        ("B", "2026-01-06"),
        ("A", "2026-01-12"),
        ("B", "2026-01-12"),
    ]
    assert [snapshot.as_of_date for snapshot in result.snapshots] == [
        "2026-01-06",
        "2026-01-12",
    ]
    assert [snapshot.profile_id for snapshot in result.snapshots] == [
        "r020-hand-calculated-golden",
        "r020-hand-calculated-golden",
    ]
    assert [snapshot.strategy_config for snapshot in result.snapshots] == [
        {"regime": "Trend"},
        {"regime": "Trend"},
    ]
    assert [snapshot.regime for snapshot in result.snapshots] == ["Trend", "Trend"]
    assert result.snapshots[0].diagnostics == []
    assert result.snapshots[0].recommendations == expected_rows
    assert result.snapshots[1].diagnostics == []
    assert result.snapshots[1].recommendations == []

    # 同一 portfolio parent 下兩個 cutoff 都有 typed child；後者是合法空決策。
    parent_id = result.replay_parent_id
    assert isinstance(parent_id, str) and parent_id.startswith("replay-parent-")
    assert {snapshot.replay_parent_id for snapshot in result.snapshots} == {parent_id}
    first_child, empty_child = [
        snapshot.canonical_execution for snapshot in result.snapshots
    ]
    assert first_child is not None
    assert empty_child is not None
    for snapshot, child in zip(result.snapshots, (first_child, empty_child)):
        assert child.status.value == "completed"
        assert child.request.as_of_date == date.fromisoformat(snapshot.as_of_date)
        assert child.context.as_of_date == date.fromisoformat(snapshot.as_of_date)
        assert child.request.top_n == 2
        assert len(child.related_references) == 1
        assert child.related_references[0].kind.value == "replay_parent"
        assert child.related_references[0].reference_id == parent_id
    assert [
        (item.stock_code, item.stock_name, item.rule_score, item.indicator_score,
         item.pattern_score, item.volume_score, item.reason_text)
        for item in first_child.decision.items
    ] == [
        ("A", "Alpha", 90.0, 70.0, 60.0, 50.0, "fixture_reason"),
        ("B", "Beta", 80.0, 65.0, 55.0, 45.0, "fixture_reason"),
    ]
    assert [assessment.stock_code for assessment in first_child.decision.assessments] == ["A", "B"]
    assert empty_child.decision.items == ()
    assert empty_child.decision.assessments == ()

    # Manifest 預期直接由 R005 factor projection 規格固定，第二日仍保留日期但無 records。
    expected_factor_records = [
        {
            "factor_name": "technical.total_score",
            "stock_code": "A",
            "as_of_date": "2026-01-06",
            "available_date": "2026-01-06",
            "value": "90.0",
            "score_bp": 9000,
            "quality": "observed",
            "missing_policy": "fail_closed",
            "source_version": "technical-v1",
            "metadata": {},
        },
        {
            "factor_name": "volume.volume_ratio",
            "stock_code": "A",
            "as_of_date": "2026-01-06",
            "available_date": "2026-01-06",
            "value": "50.0",
            "score_bp": 5000,
            "quality": "observed",
            "missing_policy": "neutral",
            "source_version": "volume-v1",
            "metadata": {"source_field": "factor_scores.volume"},
        },
        {
            "factor_name": "technical.total_score",
            "stock_code": "B",
            "as_of_date": "2026-01-06",
            "available_date": "2026-01-06",
            "value": "80.0",
            "score_bp": 8000,
            "quality": "observed",
            "missing_policy": "fail_closed",
            "source_version": "technical-v1",
            "metadata": {},
        },
        {
            "factor_name": "volume.volume_ratio",
            "stock_code": "B",
            "as_of_date": "2026-01-06",
            "available_date": "2026-01-06",
            "value": "45.0",
            "score_bp": 4500,
            "quality": "observed",
            "missing_policy": "neutral",
            "source_version": "volume-v1",
            "metadata": {"source_field": "factor_scores.volume"},
        },
    ]
    expected_contributions = {
        code: [
            {
                "factor_name": "technical.total_score",
                "state": "accepted",
                "score_bp": score_bp,
                "quality": "observed",
            },
            {
                "factor_name": "volume.volume_ratio",
                "state": "accepted",
                "score_bp": volume_bp,
                "quality": "observed",
            },
        ]
        for code, score_bp, volume_bp in (("A", 9000, 5000), ("B", 8000, 4500))
    }
    expected_factor_summary = {
        factor: {
            "accepted_count": 2,
            "neutralized_count": 0,
            "skipped_count": 0,
            "diagnostic_count": 0,
        }
        for factor in ("technical.total_score", "volume.volume_ratio")
    }
    assert result.details["data_manifest"] == {
        "factor_snapshot": {
            "schema_version": 1,
            "factor_set_version": "factor-layer-v1",
            "decision_date": "2026-01-12",
            "decision_dates": ["2026-01-06", "2026-01-12"],
            "records": expected_factor_records,
            "neutralized": [],
            "skipped": [],
            "diagnostics": [],
        },
        "factor_contributions": {
            "schema_version": 1,
            "factor_set_version": "factor-layer-v1",
            "by_stock": expected_contributions,
            "summary_by_factor": expected_factor_summary,
        },
    }

    # 以兩筆各 500,000 元持倉獨立計算：A 100→110、B 200→180，損益互抵。
    assert result.period_holdings_dataframe().to_dict(orient="records") == [
        {
            "再平衡日": "2026-01-06",
            "股票代號": "A",
            "股票名稱": "Alpha",
            "排名": 1,
            "總分": 90.0,
            "配置金額": 500000.0,
            "配置權重": 0.5,
            "實際配置權重": 0.5,
            "進場日": "2026-01-06",
            "進場價": 100.0,
            "預計出場日": "2026-01-08",
            "實際出場日": "2026-01-08",
            "實際出場價": 110.0,
            "出場原因": "holding_period",
            "持有天數": 2,
            "報酬率": 0.1,
            "損益": 50000.0,
        },
        {
            "再平衡日": "2026-01-06",
            "股票代號": "B",
            "股票名稱": "Beta",
            "排名": 2,
            "總分": 80.0,
            "配置金額": 500000.0,
            "配置權重": 0.5,
            "實際配置權重": 0.5,
            "進場日": "2026-01-06",
            "進場價": 200.0,
            "預計出場日": "2026-01-08",
            "實際出場日": "2026-01-08",
            "實際出場價": 180.0,
            "出場原因": "holding_period",
            "持有天數": 2,
            "報酬率": -0.1,
            "損益": -50000.0,
        },
    ]
    assert result.details["cash_ledger"] == [
        {"date": "2026-01-06", "stock_code": "A", "event": "buy", "amount": -500000.0, "cash_balance": 500000.0},
        {"date": "2026-01-06", "stock_code": "B", "event": "buy", "amount": -500000.0, "cash_balance": 0.0},
        {"date": "2026-01-08", "stock_code": "A", "event": "sell", "amount": 550000.0, "cash_balance": 550000.0},
        {"date": "2026-01-08", "stock_code": "B", "event": "sell", "amount": 450000.0, "cash_balance": 1000000.0},
    ]
    assert result.equity_curve.to_dict(orient="records") == [
        {"date": "2026-01-06", "equity": 1000000.0},
        {"date": "2026-01-07", "equity": 1000000.0},
        {"date": "2026-01-08", "equity": 1000000.0},
        {"date": "2026-01-09", "equity": 1000000.0},
        {"date": "2026-01-12", "equity": 1000000.0},
        {"date": "2026-01-13", "equity": 1000000.0},
    ]
    assert result.trades.to_dict(orient="records") == [
        {"date": "2026-01-06", "stock_code": "A", "stock_name": "Alpha", "side": "buy", "price": 100.0, "amount": 500000.0},
        {"date": "2026-01-08", "stock_code": "A", "stock_name": "Alpha", "side": "sell", "price": 110.0, "amount": 550000.0},
        {"date": "2026-01-06", "stock_code": "B", "stock_name": "Beta", "side": "buy", "price": 200.0, "amount": 500000.0},
        {"date": "2026-01-08", "stock_code": "B", "stock_name": "Beta", "side": "sell", "price": 180.0, "amount": 450000.0},
    ]
    assert [
        (item.stock_code, item.stock_name, item.selected_count, item.total_pnl,
         item.avg_return_pct, item.win_rate, item.worst_return_pct)
        for item in result.stock_contribution
    ] == [
        ("A", "Alpha", 1, 50000.0, 0.1, 1.0, 0.1),
        ("B", "Beta", 1, -50000.0, -0.1, 0.0, -0.1),
    ]

    expected_summary = {
        "total_return": 0.0,
        "max_drawdown": 0.0,
        "total_trades": 2,
        "avg_holding_days": 2.0,
        "capital_used": 1000000.0,
        "execution_assumption": "idealized_same_day_close",
        "execution_contract": "legacy-same-day-close.v1",
        "credibility_status": "limited",
        "credibility_warning_count": 3,
        "unfilled_order_count": 0,
        "ending_cash": 1000000.0,
        "total_transaction_cost": 0.0,
        "stop_loss_exits": 0,
        "take_profit_exits": 0,
        "holding_period_exits": 2,
        "loss_trade_ratio": 0.5,
        "worst_stock_code": "B",
        "worst_stock_name": "Beta",
        "worst_stock_pnl": -50000.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "rolling_risk_status": "insufficient_observations",
        "microstructure_risk_count": 0,
        "relative_attribution_status": "missing_optional_sources",
        "benchmark_excess_return_bp": None,
    }
    for key, expected in expected_summary.items():
        assert result.summary[key] == expected
    for key in (
        "monte_carlo_p05_return",
        "monte_carlo_p50_return",
        "monte_carlo_p95_return",
    ):
        # 任意排列的兩筆交易都只有 (1 + 10%) × (1 - 10%) = 0.99。
        assert result.summary[key] == pytest.approx(-0.01)


class _PitBoundaryScorer:
    """記錄訊號 cutoff 實際送入 scorer 的可用列，並回傳固定 R005 分數。"""

    _scores = {"P19": 70, "A": 85, "B": 91}

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def generate_recommendations(
        self, stock_data: pd.DataFrame, config: dict
    ) -> pd.DataFrame:
        stock_code = str(stock_data["證券代號"].iloc[0])
        usable_dates = tuple(
            pd.to_datetime(stock_data["日期"]).dt.strftime("%Y-%m-%d").tolist()
        )
        self.calls.append((stock_code, usable_dates))
        result = stock_data.copy()
        result["FinalScore"] = self._scores[stock_code]
        return result


def _pit_boundary_history() -> tuple[pd.DataFrame, dict[str, tuple[str, ...]]]:
    """建立 19/20/21 筆可得歷史及 cutoff 後才可用的出場價格。"""

    historical_dates = pd.bdate_range(end="2026-09-04", periods=21)
    candidates = {
        "P19": ("Nineteen", (55, 45, 35, 25, 15), 30),
        "A": ("甲股", (10, 20, 30, 40, 50), 100),
        "B": ("乙股", (11.5, 21.5, 31.5, 41.5, 51.5), 200),
    }
    rows: list[dict[str, object]] = []
    expected_scorer_dates: dict[str, tuple[str, ...]] = {}
    for code, (name, factors, entry_price) in candidates.items():
        stock_dates: list[str] = []
        for index, timestamp in enumerate(historical_dates):
            availability: object = int(timestamp.strftime("%Y%m%d"))
            if code == "P19" and index == 3:
                availability = None
            elif code == "P19" and index == 15:
                availability = 20260907
            elif code == "A" and index == 9:
                availability = "invalid-availability"
            else:
                stock_dates.append(timestamp.strftime("%Y-%m-%d"))
            rows.append(
                {
                    "日期": int(timestamp.strftime("%Y%m%d")),
                    "available_date": availability,
                    "證券代號": code,
                    "證券名稱": name,
                    "收盤價": entry_price,
                    "成交股數": 1000,
                    "oracle_score": {"P19": 70, "A": 85, "B": 91}[code],
                    "IndicatorScore": factors[0],
                    "PatternScore": factors[1],
                    "VolumeScore": factors[2],
                    "BrokerFlowScore": factors[3],
                    "RevenueScore": factors[4],
                }
            )
        expected_scorer_dates[code] = tuple(stock_dates)

    # 這三列在 9/4 訊號時點尚未出現，不可送入 scorer；回測可用它們作
    # 9/7 出場報價，避免把未來價格混入推薦輸入。
    for code, (name, factors, _) in candidates.items():
        prices = {"P19": 30, "A": 110, "B": 180}
        for timestamp in pd.to_datetime(["2026-09-07", "2026-09-08", "2026-09-09"]):
            rows.append(
                {
                    "日期": int(timestamp.strftime("%Y%m%d")),
                    "available_date": int(timestamp.strftime("%Y%m%d")),
                    "證券代號": code,
                    "證券名稱": name,
                    "收盤價": prices[code],
                    "成交股數": 1000,
                    "oracle_score": {"P19": 70, "A": 85, "B": 91}[code],
                    "IndicatorScore": factors[0],
                    "PatternScore": factors[1],
                    "VolumeScore": factors[2],
                    "BrokerFlowScore": factors[3],
                    "RevenueScore": factors[4],
                }
            )
    return pd.DataFrame(rows), expected_scorer_dates


class _PitBoundaryReasonEngine:
    def generate_reasons(self, latest_row: pd.Series, config: dict) -> list[str]:
        return ["fixture_reason"]

    def format_reason_text(self, reasons: list[str], max_reasons: int = 3) -> str:
        return "|".join(reasons[:max_reasons])


def test_concrete_provider_portfolio_fixed_vector_with_pit_and_weekend_cutoff():
    history, expected_dates = _pit_boundary_history()
    scorer = _PitBoundaryScorer()
    provider = RecommendationDataFrameProvider()
    provider.strategy_configurator = scorer
    provider.reason_engine = _PitBoundaryReasonEngine()
    config = {
        "regime": "bull",
        "filters": {"price_change_min": "0"},
        "ranking": {"top_n": 2},
        "_portfolio_lookback_days": 80,
    }

    # R005 frozen row oracle：A=85/(10,20,30,40,50)、B=91/(11.5,21.5,31.5,41.5,51.5)。
    # 只有 A（20 筆）與 B（21 筆）達 20-row 門檻；P19 有兩列不可得，A 有一列無效。
    with pytest.warns(UserWarning, match="同日收盤訊號同日收盤成交"):
        result = RecommendationPortfolioBacktestService(provider).run_portfolio_backtest(
            start_date="2026-09-04",
            end_date="2026-09-09",
            profile_id="r020-pit-fixed-vector",
            recommendation_config=config,
            history=history,
            initial_capital=1_000_000,
            rebalance_frequency="once",
            top_n=2,
            allocation_method="equal_weight",
            holding_days=3,
            execution_contract="legacy-same-day-close.v1",
        )

    expected_rows = [
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
    ]
    assert {code: len(dates) for code, dates in expected_dates.items()} == {
        "P19": 19,
        "A": 20,
        "B": 21,
    }
    snapshot = result.snapshots[0]
    assert snapshot.as_of_date == "2026-09-04"
    assert snapshot.recommendations == expected_rows
    assert snapshot.diagnostics == ["unavailable_rows_excluded:3"]
    assert [(code, len(dates), dates) for code, dates in scorer.calls] == [
        ("A", 20, expected_dates["A"]),
        ("B", 21, expected_dates["B"]),
    ]
    assert all(max(dates) == "2026-09-04" for _, dates in scorer.calls)
    assert snapshot.canonical_execution is not None
    assert [item.stock_code for item in snapshot.canonical_execution.decision.items] == [
        "B",
        "A",
    ]
    assert [
        item.stock_code for item in snapshot.canonical_execution.decision.assessments
    ] == ["B", "A"]

    # Factor records由 R005 frozen 欄位投影固定；只有實際選取的兩檔進 manifest。
    factor_snapshot = result.details["data_manifest"]["factor_snapshot"]
    assert factor_snapshot == {
        "schema_version": 1,
        "factor_set_version": "factor-layer-v1",
        "decision_date": "2026-09-04",
        "decision_dates": ["2026-09-04"],
        "records": [
            {
                "factor_name": "technical.total_score",
                "stock_code": "B",
                "as_of_date": "2026-09-04",
                "available_date": "2026-09-04",
                "value": "91.0",
                "score_bp": 9100,
                "quality": "observed",
                "missing_policy": "fail_closed",
                "source_version": "technical-v1",
                "metadata": {},
            },
            {
                "factor_name": "volume.volume_ratio",
                "stock_code": "B",
                "as_of_date": "2026-09-04",
                "available_date": "2026-09-04",
                "value": "31.5",
                "score_bp": 3150,
                "quality": "observed",
                "missing_policy": "neutral",
                "source_version": "volume-v1",
                "metadata": {"source_field": "factor_scores.volume"},
            },
            {
                "factor_name": "technical.total_score",
                "stock_code": "A",
                "as_of_date": "2026-09-04",
                "available_date": "2026-09-04",
                "value": "85.0",
                "score_bp": 8500,
                "quality": "observed",
                "missing_policy": "fail_closed",
                "source_version": "technical-v1",
                "metadata": {},
            },
            {
                "factor_name": "volume.volume_ratio",
                "stock_code": "A",
                "as_of_date": "2026-09-04",
                "available_date": "2026-09-04",
                "value": "30.0",
                "score_bp": 3000,
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
    assert result.details["data_manifest"]["factor_contributions"] == {
        "schema_version": 1,
        "factor_set_version": "factor-layer-v1",
        "by_stock": {
            "B": [
                {"factor_name": "technical.total_score", "state": "accepted", "score_bp": 9100, "quality": "observed"},
                {"factor_name": "volume.volume_ratio", "state": "accepted", "score_bp": 3150, "quality": "observed"},
            ],
            "A": [
                {"factor_name": "technical.total_score", "state": "accepted", "score_bp": 8500, "quality": "observed"},
                {"factor_name": "volume.volume_ratio", "state": "accepted", "score_bp": 3000, "quality": "observed"},
            ],
        },
        "summary_by_factor": {
            "technical.total_score": {"accepted_count": 2, "neutralized_count": 0, "skipped_count": 0, "diagnostic_count": 0},
            "volume.volume_ratio": {"accepted_count": 2, "neutralized_count": 0, "skipped_count": 0, "diagnostic_count": 0},
        },
    }

    assert result.period_holdings_dataframe().to_dict(orient="records") == [
        {
            "再平衡日": "2026-09-04", "股票代號": "B", "股票名稱": "乙股",
            "排名": 1, "總分": 91.0, "配置金額": 500000.0, "配置權重": 0.5,
            "實際配置權重": 0.5, "進場日": "2026-09-04", "進場價": 200.0,
            "預計出場日": "2026-09-07", "實際出場日": "2026-09-07", "實際出場價": 180.0,
            "出場原因": "holding_period", "持有天數": 3, "報酬率": -0.1, "損益": -50000.0,
        },
        {
            "再平衡日": "2026-09-04", "股票代號": "A", "股票名稱": "甲股",
            "排名": 2, "總分": 85.0, "配置金額": 500000.0, "配置權重": 0.5,
            "實際配置權重": 0.5, "進場日": "2026-09-04", "進場價": 100.0,
            "預計出場日": "2026-09-07", "實際出場日": "2026-09-07", "實際出場價": 110.0,
            "出場原因": "holding_period", "持有天數": 3, "報酬率": 0.1, "損益": 50000.0,
        },
    ]
    assert result.details["cash_ledger"] == [
        {"date": "2026-09-04", "stock_code": "B", "event": "buy", "amount": -500000.0, "cash_balance": 500000.0},
        {"date": "2026-09-04", "stock_code": "A", "event": "buy", "amount": -500000.0, "cash_balance": 0.0},
        {"date": "2026-09-07", "stock_code": "B", "event": "sell", "amount": 450000.0, "cash_balance": 450000.0},
        {"date": "2026-09-07", "stock_code": "A", "event": "sell", "amount": 550000.0, "cash_balance": 1000000.0},
    ]
    assert result.equity_curve.to_dict(orient="records") == [
        {"date": "2026-09-04", "equity": 1000000.0},
        {"date": "2026-09-07", "equity": 1000000.0},
        {"date": "2026-09-08", "equity": 1000000.0},
        {"date": "2026-09-09", "equity": 1000000.0},
    ]
    assert result.trades.to_dict(orient="records") == [
        {"date": "2026-09-04", "stock_code": "B", "stock_name": "乙股", "side": "buy", "price": 200.0, "amount": 500000.0},
        {"date": "2026-09-07", "stock_code": "B", "stock_name": "乙股", "side": "sell", "price": 180.0, "amount": 450000.0},
        {"date": "2026-09-04", "stock_code": "A", "stock_name": "甲股", "side": "buy", "price": 100.0, "amount": 500000.0},
        {"date": "2026-09-07", "stock_code": "A", "stock_name": "甲股", "side": "sell", "price": 110.0, "amount": 550000.0},
    ]
    assert [
        (item.stock_code, item.selected_count, item.total_pnl, item.avg_return_pct, item.win_rate, item.worst_return_pct)
        for item in result.stock_contribution
    ] == [
        ("A", 1, 50000.0, 0.1, 1.0, 0.1),
        ("B", 1, -50000.0, -0.1, 0.0, -0.1),
    ]
    assert result.summary == {
        "total_return": 0.0,
        "max_drawdown": 0.0,
        "total_trades": 2,
        "avg_holding_days": 3.0,
        "capital_used": 1000000.0,
        "execution_assumption": "idealized_same_day_close",
        "execution_contract": "legacy-same-day-close.v1",
        "credibility_status": "limited",
        "credibility_warning_count": 3,
        "unfilled_order_count": 0,
        "ending_cash": 1000000.0,
        "total_transaction_cost": 0.0,
        "stop_loss_exits": 0,
        "take_profit_exits": 0,
        "holding_period_exits": 2,
        "loss_trade_ratio": 0.5,
        "worst_stock_code": "B",
        "worst_stock_name": "乙股",
        "worst_stock_pnl": -50000.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "monte_carlo_p05_return": pytest.approx(-0.01),
        "monte_carlo_p50_return": pytest.approx(-0.01),
        "monte_carlo_p95_return": pytest.approx(-0.01),
        "rolling_risk_status": "insufficient_observations",
        "microstructure_risk_count": 0,
        "relative_attribution_status": "missing_optional_sources",
        "benchmark_excess_return_bp": None,
    }

    # R005 同一日以外的週末 cutoff 仍應採最後可得交易列；週一至週三出場價不能進 scorer。
    weekend_scorer = _PitBoundaryScorer()
    weekend_provider = RecommendationDataFrameProvider()
    weekend_provider.strategy_configurator = weekend_scorer
    weekend_provider.reason_engine = _PitBoundaryReasonEngine()
    weekend_snapshot = RecommendationReplayService(weekend_provider).run_snapshot(
        as_of_date="2026-09-06",
        profile_id="r020-pit-weekend-fixed-vector",
        config=config,
        history=history,
        universe=None,
        top_n=2,
    )
    assert weekend_snapshot.as_of_date == "2026-09-06"
    assert weekend_snapshot.recommendations == expected_rows
    assert weekend_snapshot.diagnostics == ["unavailable_rows_excluded:3"]
    assert [(code, len(dates), dates) for code, dates in weekend_scorer.calls] == [
        ("A", 20, expected_dates["A"]),
        ("B", 21, expected_dates["B"]),
    ]
    assert all(max(dates) == "2026-09-04" for _, dates in weekend_scorer.calls)
    assert weekend_snapshot.canonical_execution is not None
    assert weekend_snapshot.canonical_execution.request.as_of_date == date(2026, 9, 6)


def test_next_open_portfolio_caller_keeps_pit_snapshot_factor_golden() -> None:
    history, _ = _pit_boundary_history()
    history = history.copy()
    history["開盤價"] = None
    next_session = history["日期"] == 20260907
    open_by_code = {"P19": 31, "A": 111, "B": 181}
    history.loc[next_session, "開盤價"] = history.loc[next_session, "證券代號"].map(
        open_by_code
    )

    scorer = _PitBoundaryScorer()
    provider = RecommendationDataFrameProvider()
    provider.strategy_configurator = scorer
    provider.reason_engine = _PitBoundaryReasonEngine()
    config = {
        "regime": "bull",
        "filters": {"price_change_min": "0"},
        "ranking": {"top_n": 2},
        "_portfolio_lookback_days": 80,
    }

    result = RecommendationPortfolioBacktestService(provider).run_portfolio_backtest(
        start_date="2026-09-04",
        end_date="2026-09-09",
        profile_id="r020-pit-next-open-fixed-vector",
        recommendation_config=config,
        history=history,
        initial_capital="1000000",
        rebalance_frequency="once",
        top_n=2,
        allocation_method="equal_weight",
        holding_days=3,
        execution_contract=NEXT_OPEN_CONTRACT,
    )

    expected_rows = [
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
    ]
    snapshot = result.snapshots[0]
    assert len(result.snapshots) == 1
    assert snapshot.as_of_date == "2026-09-04"
    assert snapshot.profile_id == "r020-pit-next-open-fixed-vector"
    assert snapshot.strategy_config == config
    assert snapshot.regime == "bull"
    assert snapshot.recommendations == expected_rows
    assert snapshot.diagnostics == ["unavailable_rows_excluded:3"]

    # scorer 僅收到 cutoff 前仍可用的列；P19 剩 19 列而未呼叫 scorer。
    assert scorer.calls == [
        (
            "A",
            (
                "2026-08-07",
                "2026-08-10",
                "2026-08-11",
                "2026-08-12",
                "2026-08-13",
                "2026-08-14",
                "2026-08-17",
                "2026-08-18",
                "2026-08-19",
                "2026-08-21",
                "2026-08-24",
                "2026-08-25",
                "2026-08-26",
                "2026-08-27",
                "2026-08-28",
                "2026-08-31",
                "2026-09-01",
                "2026-09-02",
                "2026-09-03",
                "2026-09-04",
            ),
        ),
        (
            "B",
            (
                "2026-08-07",
                "2026-08-10",
                "2026-08-11",
                "2026-08-12",
                "2026-08-13",
                "2026-08-14",
                "2026-08-17",
                "2026-08-18",
                "2026-08-19",
                "2026-08-20",
                "2026-08-21",
                "2026-08-24",
                "2026-08-25",
                "2026-08-26",
                "2026-08-27",
                "2026-08-28",
                "2026-08-31",
                "2026-09-01",
                "2026-09-02",
                "2026-09-03",
                "2026-09-04",
            ),
        ),
    ]
    assert all(max(dates) == "2026-09-04" for _, dates in scorer.calls)

    assert snapshot.canonical_execution is not None
    assert snapshot.canonical_execution.request.as_of_date == date(2026, 9, 4)
    assert snapshot.canonical_execution.context.as_of_date == date(2026, 9, 4)
    assert [item.stock_code for item in snapshot.canonical_execution.decision.items] == [
        "B",
        "A",
    ]
    assert [
        item.stock_code for item in snapshot.canonical_execution.decision.assessments
    ] == ["B", "A"]

    assert result.details["data_manifest"]["factor_snapshot"] == {
        "schema_version": 1,
        "factor_set_version": "factor-layer-v1",
        "decision_date": "2026-09-04",
        "decision_dates": ["2026-09-04"],
        "records": [
            {
                "factor_name": "technical.total_score",
                "stock_code": "B",
                "as_of_date": "2026-09-04",
                "available_date": "2026-09-04",
                "value": "91.0",
                "score_bp": 9100,
                "quality": "observed",
                "missing_policy": "fail_closed",
                "source_version": "technical-v1",
                "metadata": {},
            },
            {
                "factor_name": "volume.volume_ratio",
                "stock_code": "B",
                "as_of_date": "2026-09-04",
                "available_date": "2026-09-04",
                "value": "31.5",
                "score_bp": 3150,
                "quality": "observed",
                "missing_policy": "neutral",
                "source_version": "volume-v1",
                "metadata": {"source_field": "factor_scores.volume"},
            },
            {
                "factor_name": "technical.total_score",
                "stock_code": "A",
                "as_of_date": "2026-09-04",
                "available_date": "2026-09-04",
                "value": "85.0",
                "score_bp": 8500,
                "quality": "observed",
                "missing_policy": "fail_closed",
                "source_version": "technical-v1",
                "metadata": {},
            },
            {
                "factor_name": "volume.volume_ratio",
                "stock_code": "A",
                "as_of_date": "2026-09-04",
                "available_date": "2026-09-04",
                "value": "30.0",
                "score_bp": 3000,
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
    assert result.details["data_manifest"]["factor_contributions"] == {
        "schema_version": 1,
        "factor_set_version": "factor-layer-v1",
        "by_stock": {
            "B": [
                {"factor_name": "technical.total_score", "state": "accepted", "score_bp": 9100, "quality": "observed"},
                {"factor_name": "volume.volume_ratio", "state": "accepted", "score_bp": 3150, "quality": "observed"},
            ],
            "A": [
                {"factor_name": "technical.total_score", "state": "accepted", "score_bp": 8500, "quality": "observed"},
                {"factor_name": "volume.volume_ratio", "state": "accepted", "score_bp": 3000, "quality": "observed"},
            ],
        },
        "summary_by_factor": {
            "technical.total_score": {"accepted_count": 2, "neutralized_count": 0, "skipped_count": 0, "diagnostic_count": 0},
            "volume.volume_ratio": {"accepted_count": 2, "neutralized_count": 0, "skipped_count": 0, "diagnostic_count": 0},
        },
    }
    assert result.details["data_manifest"]["execution_contract"] == NEXT_OPEN_CONTRACT

    # 只固定 next-open 的成交日期；不把其帳務結果與 legacy-close 比較。
    assert [
        (row["date"], row["signal_date"], row["stock_code"], row["side"])
        for row in result.trades.to_dict(orient="records")
    ] == [
        ("2026-09-07", "2026-09-04", "B", "buy"),
        ("2026-09-07", "2026-09-04", "A", "buy"),
    ]

    # 獨立手算 next-open 帳本：B/A 各配置 500,000，依 181/111 開盤價買入
    # 2,762/4,504 股；不含成本時餘額 134，9/7 收盤持倉市值為 992,600。
    assert result.trades.to_dict(orient="records") == [
        {
            "date": "2026-09-07",
            "stock_code": "B",
            "stock_name": "乙股",
            "side": "buy",
            "price": 181.0,
            "amount": 499922.0,
            "requested_shares": 2762,
            "shares": 2762,
            "unfilled_shares": 0,
            "fee": 0.0,
            "tax": 0.0,
            "slippage": 0.0,
            "fill_status": "filled",
            "fill_reason": None,
            "execution_contract": NEXT_OPEN_CONTRACT,
            "signal_date": "2026-09-04",
        },
        {
            "date": "2026-09-07",
            "stock_code": "A",
            "stock_name": "甲股",
            "side": "buy",
            "price": 111.0,
            "amount": 499944.0,
            "requested_shares": 4504,
            "shares": 4504,
            "unfilled_shares": 0,
            "fee": 0.0,
            "tax": 0.0,
            "slippage": 0.0,
            "fill_status": "filled",
            "fill_reason": None,
            "execution_contract": NEXT_OPEN_CONTRACT,
            "signal_date": "2026-09-04",
        },
    ]
    assert result.period_holdings_dataframe().to_dict(orient="records") == [
        {
            "再平衡日": "2026-09-04",
            "股票代號": "B",
            "股票名稱": "乙股",
            "排名": 1,
            "總分": 91.0,
            "配置金額": 499922.0,
            "配置權重": 0.5,
            "實際配置權重": 0.499922,
            "進場日": "2026-09-07",
            "進場價": 181.0,
            "預計出場日": "2026-09-10",
            "實際出場日": "",
            "實際出場價": 0.0,
            "出場原因": "end_of_data_open",
            "持有天數": 2,
            "報酬率": -0.0055248618784530384,
            "損益": -2762.0,
        },
        {
            "再平衡日": "2026-09-04",
            "股票代號": "A",
            "股票名稱": "甲股",
            "排名": 2,
            "總分": 85.0,
            "配置金額": 499944.0,
            "配置權重": 0.5,
            "實際配置權重": 0.499944,
            "進場日": "2026-09-07",
            "進場價": 111.0,
            "預計出場日": "2026-09-10",
            "實際出場日": "",
            "實際出場價": 0.0,
            "出場原因": "end_of_data_open",
            "持有天數": 2,
            "報酬率": -0.009009009009009009,
            "損益": -4504.0,
        },
    ]
    assert result.details["cash_ledger"] == [
        {
            "date": "2026-09-07",
            "stock_code": "B",
            "side": "buy",
            "amount": 499922.0,
            "total_cost": 0.0,
            "cash_balance": 500078.0,
        },
        {
            "date": "2026-09-07",
            "stock_code": "A",
            "side": "buy",
            "amount": 499944.0,
            "total_cost": 0.0,
            "cash_balance": 134.0,
        },
    ]
    assert result.equity_curve.to_dict(orient="records") == [
        {
            "date": "2026-09-04",
            "cash": 1000000.0,
            "position_value": 0.0,
            "equity": 1000000.0,
        },
        {
            "date": "2026-09-07",
            "cash": 134.0,
            "position_value": 992600.0,
            "equity": 992734.0,
        },
        {
            "date": "2026-09-08",
            "cash": 134.0,
            "position_value": 992600.0,
            "equity": 992734.0,
        },
        {
            "date": "2026-09-09",
            "cash": 134.0,
            "position_value": 992600.0,
            "equity": 992734.0,
        },
    ]
    summary = result.summary
    assert {
        key: summary[key]
        for key in (
            "execution_contract",
            "execution_assumption",
            "status",
            "total_trades",
            "open_position_count",
            "unfilled_order_count",
            "ending_cash",
            "ending_cash_cents",
            "ending_equity",
            "ending_equity_cents",
            "total_transaction_cost",
            "realized_pnl",
            "unrealized_pnl",
            "total_return",
            "max_drawdown",
        )
    } == {
        "execution_contract": NEXT_OPEN_CONTRACT,
        "execution_assumption": "next_session_open",
        "status": "completed",
        "total_trades": 0,
        "open_position_count": 2,
        "unfilled_order_count": 0,
        "ending_cash": 134.0,
        "ending_cash_cents": 13400,
        "ending_equity": 992734.0,
        "ending_equity_cents": 99273400,
        "total_transaction_cost": 0.0,
        "realized_pnl": 0.0,
        "unrealized_pnl": -7266.0,
        "total_return": -0.007266,
        "max_drawdown": -0.007266,
    }

    # Parent 是 invocation 專屬 identity；typed child 必須明確且唯一地引用它。
    parent_id = result.replay_parent_id
    assert parent_id.startswith("replay-parent-")
    assert snapshot.replay_parent_id == parent_id
    assert snapshot.canonical_execution is not None
    child = snapshot.canonical_execution
    assert child.result_id != parent_id
    assert len(child.related_references) == 1
    assert child.related_references[0].kind.value == "replay_parent"
    assert child.related_references[0].reference_id == parent_id
