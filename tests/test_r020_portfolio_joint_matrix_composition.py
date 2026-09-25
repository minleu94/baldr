"""R020 portfolio caller 的 scorer、v1 rows 與帳務聯合固定向量。"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest

from backtest_module.broker_simulator import LEGACY_CLOSE_CONTRACT
from app_module.recommendation_dataframe_provider import (
    RecommendationDataFrameProvider,
    ReplayProviderCallResultV1,
)
from app_module.recommendation_portfolio_backtest_service import (
    RecommendationPortfolioBacktestService,
)
from decision_module.recommendation.evaluate import (
    NeedCandidateScoring,
    RecommendationEvaluator,
    ReplayCandidatePrefilterStep,
    ReplayCandidateScoringOutcomeV1,
    ReplayScorerDispositionV1,
    ReplayScorerResponseV1,
)
from test_r020_replay_pipeline_composition import (
    _MatrixReasonEngine,
    _MatrixScorer,
    _history,
)


_CUTOFF = date(2026, 9, 4)


class _PortfolioMatrixScorer(_MatrixScorer):
    """記錄同次 portfolio invocation 真正送入 scorer 的日期列。"""

    def __init__(self) -> None:
        super().__init__(
            {
                "HI": 100.0,
                "SELECTED_PROJECTION": 95.0,
                "MID": 90.0,
                "SECOND_PROJECTION": 80.0,
                "TAIL": 70.0,
            },
            empty_codes={"EMPTY"},
            failing_codes={"BROKEN"},
        )
        self.input_dates: list[tuple[str, tuple[date, ...]]] = []

    def generate_recommendations(
        self, stock_data: pd.DataFrame, config: dict[str, Any]
    ) -> pd.DataFrame:
        code = str(stock_data["證券代號"].iloc[0])
        dates = tuple(pd.Timestamp(value).date() for value in stock_data["日期"])
        self.input_dates.append((code, dates))
        return super().generate_recommendations(stock_data, config)


def test_portfolio_caller_preserves_cutoff_rows_child_boundary_and_accounting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一 portfolio 呼叫固定 scorer terminal、v1 rows、child 與帳務。"""

    completed: list[tuple[str, ReplayScorerDispositionV1]] = []
    original_complete = RecommendationEvaluator.complete_replay_scoring

    def capture_completion(
        evaluator: RecommendationEvaluator,
        step: ReplayCandidatePrefilterStep,
        response: ReplayScorerResponseV1,
    ) -> ReplayCandidateScoringOutcomeV1:
        outcome = original_complete(evaluator, step, response)
        request = step.request
        assert type(request) is NeedCandidateScoring
        completed.append((request.stock_code, outcome.disposition))
        return outcome

    monkeypatch.setattr(
        RecommendationEvaluator,
        "complete_replay_scoring",
        capture_completion,
    )

    history = _history()
    # 9/4 是唯一訊號 cutoff；9/7 僅作為已持倉的出場觀測。
    for code, signal_close, exit_close in (
        ("HI", 100, 110),
        ("SELECTED_PROJECTION", 200, 180),
    ):
        signal_row = (history["證券代號"] == code) & (history["日期"] == 20260904)
        exit_row = (history["證券代號"] == code) & (history["日期"] == 20260907)
        history.loc[signal_row, "收盤價"] = signal_close
        history.loc[exit_row, "收盤價"] = exit_close
        history.loc[exit_row, "available_date"] = 20260907

    scorer = _PortfolioMatrixScorer()
    provider = RecommendationDataFrameProvider()
    setattr(provider, "strategy_configurator", scorer)
    setattr(provider, "reason_engine", _MatrixReasonEngine({"SELECTED_PROJECTION"}))

    handoffs: list[ReplayProviderCallResultV1] = []
    original_handoff = provider.run_with_as_of_handoff

    def capture_handoff(
        frame: pd.DataFrame,
        config: dict[str, Any],
        top_n: int,
        as_of_date: date,
    ) -> ReplayProviderCallResultV1:
        result = original_handoff(frame, config, top_n, as_of_date)
        handoffs.append(result)
        return result

    monkeypatch.setattr(provider, "run_with_as_of_handoff", capture_handoff)

    with pytest.warns(UserWarning, match="同日收盤訊號同日收盤成交"):
        result = RecommendationPortfolioBacktestService(
            provider
        ).run_portfolio_backtest(
            start_date="2026-09-04",
            end_date="2026-09-09",
            profile_id="r020-portfolio-joint-golden",
            recommendation_config={},
            history=history,
            initial_capital=1_000_000,
            rebalance_frequency="once",
            top_n=2,
            allocation_method="equal_weight",
            holding_days=3,
            execution_contract=LEGACY_CLOSE_CONTRACT,
        )

    assert len(result.snapshots) == 1
    snapshot = result.snapshots[0]
    assert snapshot.as_of_date == "2026-09-04"
    assert snapshot.diagnostics == ["unavailable_rows_excluded:3"]

    # 目前 Windows/Pandas 的 portfolio wrapper 先依日期排序；以下固定此
    # caller 的觀測 encounter order，不把 direct run_snapshot 順序當 portfolio oracle。
    expected_encounter = (
        "SELECTED_PROJECTION",
        "BROKEN",
        "SECOND_PROJECTION",
        "EMPTY",
        "TAIL",
        "MID",
        "HI",
    )
    assert tuple(code for code, _rows, _day in scorer.calls) == expected_encounter
    assert scorer.calls == [
        ("SELECTED_PROJECTION", 21, _CUTOFF),
        ("BROKEN", 21, _CUTOFF),
        ("SECOND_PROJECTION", 21, _CUTOFF),
        ("EMPTY", 21, _CUTOFF),
        ("TAIL", 21, _CUTOFF),
        ("MID", 21, _CUTOFF),
        ("HI", 20, _CUTOFF),
    ]
    assert tuple(code for code, _dates in scorer.input_dates) == expected_encounter
    assert all(
        all(day <= _CUTOFF for day in dates)
        for _code, dates in scorer.input_dates
    )
    assert all(
        date(2026, 9, 7) not in dates for _code, dates in scorer.input_dates
    )

    # 19-row P19 先佔 first-seen 名額再由 history gate 排除，不到 scorer。
    assert "P19" not in expected_encounter
    assert completed == [
        ("SELECTED_PROJECTION", ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION),
        ("BROKEN", ReplayScorerDispositionV1.SKIPPED_SCORER_EXCEPTION),
        ("SECOND_PROJECTION", ReplayScorerDispositionV1.SCORED),
        ("EMPTY", ReplayScorerDispositionV1.SKIPPED_EMPTY),
        ("TAIL", ReplayScorerDispositionV1.SCORED),
        ("MID", ReplayScorerDispositionV1.SCORED),
        ("HI", ReplayScorerDispositionV1.SCORED),
    ]

    assert len(handoffs) == 1
    handoff = handoffs[0]
    assert handoff.as_of_date == _CUTOFF
    assert handoff.requested_top_n == 2
    assert tuple(row["stock_code"] for row in handoff.rows) == (
        "HI",
        "SELECTED_PROJECTION",
    )
    assert len(handoff.rows) == len(handoff.scoring_outcomes) == 2
    assert [
        (outcome.request.stock_code, outcome.disposition)
        if outcome is not None
        else None
        for outcome in handoff.scoring_outcomes
    ] == [
        ("HI", ReplayScorerDispositionV1.SCORED),
        (
            "SELECTED_PROJECTION",
            ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION,
        ),
    ]
    assert all(
        outcome is not None
        and outcome.request.stock_code == row["stock_code"]
        and outcome.request.as_of_date == _CUTOFF
        for row, outcome in zip(handoff.rows, handoff.scoring_outcomes)
    )

    expected_rows = snapshot.recommendations
    assert [row["stock_code"] for row in expected_rows] == [
        "HI",
        "SELECTED_PROJECTION",
    ]
    assert expected_rows[0] == {
        "stock_code": "HI",
        "stock_name": "名稱-HI",
        "total_score": 100.0,
        "factor_scores": {
            "technical": 3.0,
            "pattern": 2.0,
            "volume": 1.0,
            "broker_flow": 0.0,
            "revenue": 0.0,
        },
        "selection_reason": "reason-HI",
    }
    selected = expected_rows[1]
    assert selected == {
        "stock_code": "SELECTED_PROJECTION",
        "stock_name": "名稱-SELECTED_PROJECTION",
        "total_score": 95.0,
        "factor_scores": {
            "technical": 3.0,
            "pattern": 2.0,
            "volume": 1.0,
            "broker_flow": 0.0,
            "revenue": 0.0,
        },
        "selection_reason": selected["selection_reason"],
    }
    assert type(selected["selection_reason"]) is object
    # 舊 v1 row 保留；選取列無法成為完整 typed child 時不發布部分 child。
    assert snapshot.canonical_execution is None
    parent_id = result.replay_parent_id
    assert isinstance(parent_id, str) and parent_id.startswith("replay-parent-")
    assert snapshot.replay_parent_id == parent_id

    assert result.period_holdings_dataframe().to_dict(orient="records") == [
        {
            "再平衡日": "2026-09-04",
            "股票代號": "HI",
            "股票名稱": "名稱-HI",
            "排名": 1,
            "總分": 100.0,
            "配置金額": 500000.0,
            "配置權重": 0.5,
            "實際配置權重": 0.5,
            "進場日": "2026-09-04",
            "進場價": 100.0,
            "預計出場日": "2026-09-07",
            "實際出場日": "2026-09-07",
            "實際出場價": 110.0,
            "出場原因": "holding_period",
            "持有天數": 3,
            "報酬率": 0.1,
            "損益": 50000.0,
        },
        {
            "再平衡日": "2026-09-04",
            "股票代號": "SELECTED_PROJECTION",
            "股票名稱": "名稱-SELECTED_PROJECTION",
            "排名": 2,
            "總分": 95.0,
            "配置金額": 500000.0,
            "配置權重": 0.5,
            "實際配置權重": 0.5,
            "進場日": "2026-09-04",
            "進場價": 200.0,
            "預計出場日": "2026-09-07",
            "實際出場日": "2026-09-07",
            "實際出場價": 180.0,
            "出場原因": "holding_period",
            "持有天數": 3,
            "報酬率": -0.1,
            "損益": -50000.0,
        },
    ]
    assert result.details["cash_ledger"] == [
        {
            "date": "2026-09-04",
            "stock_code": "HI",
            "event": "buy",
            "amount": -500000.0,
            "cash_balance": 500000.0,
        },
        {
            "date": "2026-09-04",
            "stock_code": "SELECTED_PROJECTION",
            "event": "buy",
            "amount": -500000.0,
            "cash_balance": 0.0,
        },
        {
            "date": "2026-09-07",
            "stock_code": "HI",
            "event": "sell",
            "amount": 550000.0,
            "cash_balance": 550000.0,
        },
        {
            "date": "2026-09-07",
            "stock_code": "SELECTED_PROJECTION",
            "event": "sell",
            "amount": 450000.0,
            "cash_balance": 1000000.0,
        },
    ]
    assert result.equity_curve.to_dict(orient="records") == [
        {"date": "2026-09-04", "equity": 1000000.0},
        {"date": "2026-09-07", "equity": 1000000.0},
        {"date": "2026-09-09", "equity": 1000000.0},
    ]
    assert result.trades.to_dict(orient="records") == [
        {
            "date": "2026-09-04",
            "stock_code": "HI",
            "stock_name": "名稱-HI",
            "side": "buy",
            "price": 100.0,
            "amount": 500000.0,
        },
        {
            "date": "2026-09-07",
            "stock_code": "HI",
            "stock_name": "名稱-HI",
            "side": "sell",
            "price": 110.0,
            "amount": 550000.0,
        },
        {
            "date": "2026-09-04",
            "stock_code": "SELECTED_PROJECTION",
            "stock_name": "名稱-SELECTED_PROJECTION",
            "side": "buy",
            "price": 200.0,
            "amount": 500000.0,
        },
        {
            "date": "2026-09-07",
            "stock_code": "SELECTED_PROJECTION",
            "stock_name": "名稱-SELECTED_PROJECTION",
            "side": "sell",
            "price": 180.0,
            "amount": 450000.0,
        },
    ]
    assert {
        key: result.summary[key]
        for key in (
            "ending_cash",
            "total_return",
            "total_trades",
            "total_transaction_cost",
            "worst_stock_code",
            "worst_stock_pnl",
        )
    } == {
        "ending_cash": 1_000_000.0,
        "total_return": 0.0,
        "total_trades": 2,
        "total_transaction_cost": 0.0,
        "worst_stock_code": "SELECTED_PROJECTION",
        "worst_stock_pnl": -50_000.0,
    }
