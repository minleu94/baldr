"""R020 replay parent identity 的合成契約測試。"""

from __future__ import annotations

from dataclasses import asdict, fields
from decimal import Decimal
from typing import Any

import pandas as pd
import pytest

from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
    RecommendationSnapshotDTO,
)
from app_module.recommendation_portfolio_backtest_service import (
    RecommendationPortfolioBacktestService,
)
from app_module.recommendation_replay_service import RecommendationReplayService


def _provider(
    _data: pd.DataFrame,
    _config: dict[str, Any],
    _top_n: int,
) -> list[dict[str, Any]]:
    return [
        {
            "stock_code": "2330",
            "stock_name": "合成標的",
            "total_score": Decimal("82.5"),
            "factor_scores": {
                "technical": Decimal("81"),
                "pattern": Decimal("82"),
                "volume": Decimal("83"),
            },
            "selection_reason": "合成原因",
        }
    ]


def _history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": [20260901, 20260902],
            "證券代號": ["2330", "2330"],
            "available_date": [20260901, 20260902],
        }
    )


def _run_snapshot(as_of_date: str, **kwargs: Any) -> RecommendationSnapshotDTO:
    return RecommendationReplayService(_provider).run_snapshot(
        as_of_date=as_of_date,
        profile_id="profile-r020-parent-test",
        config={"strategy_id": "synthetic-r020"},
        history=_history(),
        universe=None,
        top_n=1,
        **kwargs,
    )


def _weekly_history() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"日期": "2026-09-01", "證券代號": "2330", "收盤價": 100},
            {"日期": "2026-09-08", "證券代號": "2330", "收盤價": 101},
        ]
    )


def _empty_provider(
    _data: pd.DataFrame, _config: dict[str, Any], _top_n: int
) -> list[dict[str, Any]]:
    return []


def test_explicit_parent_stays_on_legacy_snapshot_without_child_rehydration() -> None:
    parent_result_id = "replay-parent-r020-explicit"

    snapshot = _run_snapshot(
        "2026-09-01",
        parent_result_id=parent_result_id,
    )

    assert snapshot.replay_parent_id == parent_result_id
    assert snapshot.canonical_execution is None


def test_omitted_parent_is_generated_per_snapshot_and_stays_out_of_v1_wire() -> None:
    first = _run_snapshot("2026-09-01")
    second = _run_snapshot("2026-09-02")

    assert first.replay_parent_id
    assert second.replay_parent_id
    assert first.replay_parent_id != second.replay_parent_id
    for snapshot in (first, second):
        assert snapshot.canonical_execution is None

    expected_wire_fields = {
        "as_of_date",
        "profile_id",
        "strategy_config",
        "regime",
        "recommendations",
        "diagnostics",
    }
    assert {item.name for item in fields(RecommendationSnapshotDTO)} == expected_wire_fields
    assert set(asdict(first)) == expected_wire_fields
    assert "replay_parent_id" not in asdict(first)


def test_same_parent_keeps_legacy_snapshot_identity_across_dates() -> None:
    parent_result_id = "replay-parent-r020-multi-date"

    first = _run_snapshot(
        "2026-09-01",
        parent_result_id=parent_result_id,
    )
    second = _run_snapshot(
        "2026-09-02",
        parent_result_id=parent_result_id,
    )

    assert first.replay_parent_id == second.replay_parent_id == parent_result_id
    for snapshot in (first, second):
        assert snapshot.canonical_execution is None


def test_portfolio_invocation_shares_one_parent_across_rebalance_snapshots() -> None:
    service = RecommendationPortfolioBacktestService(_empty_provider)
    with pytest.warns(UserWarning):
        result = service.run_portfolio_backtest(
            start_date="2026-09-01",
            end_date="2026-09-08",
            profile_id="profile-r020-parent-test",
            recommendation_config={},
            history=_weekly_history(),
            initial_capital=1000.0,
            rebalance_frequency="weekly",
            top_n=1,
            allocation_method="equal_weight",
            holding_days=1,
            execution_contract="legacy-same-day-close.v1",
        )

    assert len(result.snapshots) == 2
    assert result.replay_parent_id is not None
    assert {item.replay_parent_id for item in result.snapshots} == {
        result.replay_parent_id
    }
    for snapshot in result.snapshots:
        assert snapshot.canonical_execution is None
    assert "replay_parent_id" not in result.to_dict()


@pytest.mark.parametrize("case", ["empty_sessions", "first_session_cancel"])
def test_next_open_without_snapshots_retains_parent_outside_v1_wire(case: str) -> None:
    if case == "empty_sessions":
        history = pd.DataFrame(
            [{"日期": "2026-08-31", "證券代號": "2330", "收盤價": 100}]
        )
        check_cancel = None
    else:
        history = pd.DataFrame(
            [{"日期": "2026-09-01", "證券代號": "2330", "收盤價": 100}]
        )
        check_cancel = lambda: True

    result = RecommendationPortfolioBacktestService(_empty_provider).run_portfolio_backtest(
        start_date="2026-09-01",
        end_date="2026-09-08",
        profile_id="profile-r020-parent-test",
        recommendation_config={},
        history=history,
        initial_capital=1000.0,
        rebalance_frequency="weekly",
        top_n=1,
        allocation_method="equal_weight",
        holding_days=1,
        execution_contract="next-session-open.v2",
        check_cancel=check_cancel,
    )

    assert result.replay_parent_id
    assert result.snapshots == []
    encoded = result.to_dict()
    assert "replay_parent_id" not in encoded
    assert encoded["snapshots"] == []
    assert set(encoded) == {
        "summary",
        "equity_curve",
        "trades",
        "snapshots",
        "period_holdings",
        "stock_contribution",
        "selection_diagnostics",
        "improvement_hints",
        "details",
    }
    if case == "first_session_cancel":
        assert encoded["summary"]["status"] == "cancelled"


def test_next_open_portfolio_invocation_shares_parent_across_snapshots() -> None:
    result = RecommendationPortfolioBacktestService(_empty_provider).run_portfolio_backtest(
        start_date="2026-09-01",
        end_date="2026-09-08",
        profile_id="profile-r020-parent-test",
        recommendation_config={},
        history=_weekly_history(),
        initial_capital=1000.0,
        rebalance_frequency="weekly",
        top_n=1,
        allocation_method="equal_weight",
        holding_days=1,
        execution_contract="next-session-open.v2",
    )

    assert len(result.snapshots) == 2
    assert result.replay_parent_id
    assert {snapshot.replay_parent_id for snapshot in result.snapshots} == {
        result.replay_parent_id
    }
    for snapshot in result.snapshots:
        assert snapshot.canonical_execution is None
    assert "replay_parent_id" not in result.to_dict()


def test_direct_next_open_invocation_generates_one_parent_for_all_snapshots() -> None:
    result = RecommendationPortfolioBacktestService(_empty_provider)._run_next_open_portfolio(
        start_date="2026-09-01",
        end_date="2026-09-08",
        profile_id="profile-r020-parent-test",
        config={},
        history=_weekly_history(),
        initial_capital=1000.0,
        rebalance_frequency="weekly",
        top_n=1,
        allocation_method="equal_weight",
        holding_days=1,
        stop_loss_pct=None,
        take_profit_pct=None,
        max_participation_rate=None,
        fee_bps=None,
        slippage_bps=None,
        tax_bps=None,
        lot_size=None,
        check_cancel=None,
    )

    assert len(result.snapshots) == 2
    assert result.replay_parent_id
    assert {snapshot.replay_parent_id for snapshot in result.snapshots} == {
        result.replay_parent_id
    }
    for snapshot in result.snapshots:
        assert snapshot.canonical_execution is None


def test_portfolio_parent_property_rejects_known_and_unknown_snapshot_mix() -> None:
    known = _run_snapshot(
        "2026-09-01",
        parent_result_id="replay-parent-r020-mixed-known",
    )
    unknown = RecommendationSnapshotDTO(
        as_of_date="2026-09-02",
        profile_id="profile-r020-parent-test",
        strategy_config={},
        regime="",
        recommendations=[],
    )
    result = RecommendationPortfolioBacktestResultDTO(
        summary={},
        equity_curve=pd.DataFrame(),
        trades=pd.DataFrame(),
        snapshots=[known, unknown],
        period_holdings=[],
        stock_contribution=[],
    )

    with pytest.raises(ValueError, match="已知與未知 replay parent"):
        _ = result.replay_parent_id


def test_snapshot_and_portfolio_parent_ids_cannot_be_rebound() -> None:
    parent_result_id = "replay-parent-r020-rebind"
    snapshot = _run_snapshot(
        "2026-09-01",
        parent_result_id=parent_result_id,
    )

    snapshot.attach_replay_parent_id(parent_result_id)
    with pytest.raises(ValueError, match="snapshot replay parent ID 不可重新綁定"):
        snapshot.attach_replay_parent_id("replay-parent-r020-other")

    result = RecommendationPortfolioBacktestResultDTO(
        summary={},
        equity_curve=pd.DataFrame(),
        trades=pd.DataFrame(),
        snapshots=[snapshot],
        period_holdings=[],
        stock_contribution=[],
    )
    result.attach_replay_parent_id(parent_result_id)
    with pytest.raises(ValueError, match="portfolio replay parent ID 不可重新綁定"):
        result.attach_replay_parent_id("replay-parent-r020-other")
