"""R017 replay v1 compatibility 測試；所有輸入皆為合成資料與記憶體物件。"""

from __future__ import annotations

from dataclasses import asdict, fields
import json
import math
from typing import Any

import pandas as pd
import pytest

from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
    RecommendationSnapshotDTO,
)
from app_module.recommendation_replay_service import RecommendationReplayService


def _snapshot(
    provider_rows: list[Any],
    *,
    config: dict[str, Any] | None = None,
) -> RecommendationSnapshotDTO:
    frozen_config = dict(config or {"regime": "neutral"})

    def provider(
        data: pd.DataFrame, provider_config: dict[str, Any], top_n: int
    ) -> list[dict[str, Any]]:
        assert provider_config == frozen_config
        return provider_rows[:top_n]

    history = pd.DataFrame(
        {
            "日期": [20260901, 20260901],
            "證券代號": ["2330", "2317"],
            "available_date": [20260901, 20260901],
        }
    )
    return RecommendationReplayService(provider).run_snapshot(
        as_of_date="2026-09-01",
        profile_id="profile-r017-test-v1",
        config=frozen_config,
        history=history,
        universe=None,
        top_n=len(provider_rows),
    )


def _result_dto(
    snapshots: list[RecommendationSnapshotDTO],
) -> RecommendationPortfolioBacktestResultDTO:
    return RecommendationPortfolioBacktestResultDTO(
        summary={},
        equity_curve=pd.DataFrame(),
        trades=pd.DataFrame(),
        snapshots=snapshots,
        period_holdings=[],
        stock_contribution=[],
    )


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def test_legacy_rows_keep_v1_wire_shape_without_canonical_rehydration():
    annotation = {
        "probability_bp": 8123,
        "model_version": "historical-model-v1",
        "source": "stored-result",
    }
    source_refs = [{"source_id": "test-only-source", "snapshot_id": "test-only"}]
    rows = [
        {
            "stock_code": "2330",
            "recommendation_rank": 2,
            "stock_name": "台積電",
            "total_score": 82.35,
            "factor_scores": {
                "technical": 70.0,
                "pattern": 64.25,
                "volume": 40.0,
                "broker_flow": 88.0,
            },
            "selection_reason": "source reason",
            "available_date": "2026-09-01",
            "available_at": "2026-09-01T13:25:00+08:00",
            "source_refs": source_refs,
            "stored_annotation": annotation,
        },
        {
            "stock_code": "2317",
            "recommendation_rank": 1,
            "stock_name": "鴻海",
            "total_score": 71.25,
            "factor_scores": {"technical": 62.5, "pattern": 51.0, "volume": 36.5},
            "selection_reason": "second source reason",
            "stored_annotation": {"probability_bp": 7000},
        },
    ]
    config = {
        "regime": "neutral",
        "_portfolio_max_stocks": 75,
        "filters": {"price_change_min": 1.25},
    }

    snapshot = _snapshot(rows, config=config)
    assert snapshot.canonical_execution is None
    assert snapshot.replay_parent_id
    assert snapshot.strategy_config == config

    legacy_snapshot = asdict(snapshot)
    assert set(legacy_snapshot) == {
        "as_of_date",
        "profile_id",
        "strategy_config",
        "regime",
        "recommendations",
        "diagnostics",
    }
    assert legacy_snapshot["recommendations"] == rows
    assert legacy_snapshot["recommendations"][0]["stored_annotation"] == annotation
    assert legacy_snapshot["recommendations"][0]["source_refs"] == source_refs
    assert [
        row["recommendation_rank"] for row in legacy_snapshot["recommendations"]
    ] == [2, 1]

    encoded = _result_dto([snapshot]).to_dict()
    assert encoded["snapshots"] == [legacy_snapshot]
    encoded_bytes = _json_bytes(encoded)
    restored = RecommendationPortfolioBacktestResultDTO.from_dict(
        json.loads(encoded_bytes.decode("utf-8"))
    )
    restored_bytes = _json_bytes(restored.to_dict())
    assert restored_bytes == encoded_bytes
    assert restored.snapshots[0].recommendations == rows
    assert restored.snapshots[0].canonical_execution is None


def test_legacy_snapshots_receive_distinct_parent_identity_without_child():
    rows = [
        {
            "stock_code": "2330",
            "stock_name": "台積電",
            "total_score": 82.35,
            "factor_scores": {},
            "selection_reason": "fixture",
        }
    ]

    first = _snapshot(rows)
    second = _snapshot(rows)

    assert first.canonical_execution is None
    assert second.canonical_execution is None
    assert first.replay_parent_id
    assert second.replay_parent_id
    assert first.replay_parent_id != second.replay_parent_id


def test_empty_legacy_snapshot_keeps_empty_rows_without_child_execution():
    snapshot = _snapshot([])

    assert snapshot.recommendations == []
    assert snapshot.canonical_execution is None
    assert snapshot.replay_parent_id


def test_legacy_config_does_not_create_a_typed_child():
    snapshot = _snapshot(
        [{"stock_code": "2330", "total_score": 82.35}],
        config={"regime": "neutral"},
    )

    assert snapshot.canonical_execution is None
    assert snapshot.strategy_config == {"regime": "neutral"}


@pytest.mark.parametrize(
    "raw_value",
    [
        75,
        "75",
        75.0,
        2.5,
        True,
    ],
)
def test_legacy_max_stocks_values_stay_in_config_without_child_projection(
    raw_value: object,
):
    snapshot = _snapshot(
        [{"stock_code": "2330", "total_score": 82.35}],
        config={"regime": "neutral", "_portfolio_max_stocks": raw_value},
    )

    assert snapshot.canonical_execution is None
    assert snapshot.strategy_config["_portfolio_max_stocks"] == raw_value


@pytest.mark.parametrize(
    "row",
    [
        {
            "stock_code": "2330",
            "total_score": "unknown-score",
            "factor_scores": {},
        },
        {
            "stock_code": "2330",
            "total_score": 82.35,
            "factor_scores": {"technical": float("nan")},
        },
        {
            "stock_code": "2330",
            "total_score": 82.35,
            "factor_scores": {"pattern": "unknown-score"},
        },
    ],
)
def test_legacy_score_values_are_not_parsed_or_changed(
    row: dict[str, Any],
):
    snapshot = _snapshot([row])

    assert len(snapshot.recommendations) == 1
    assert snapshot.canonical_execution is None
    assert snapshot.recommendations[0] == row
    if row.get("total_score") == "unknown-score":
        assert snapshot.recommendations[0]["total_score"] == "unknown-score"
    elif math.isnan(row.get("factor_scores", {}).get("technical", 0.0)):
        assert math.isnan(
            snapshot.recommendations[0]["factor_scores"]["technical"]
        )
    else:
        assert (
            snapshot.recommendations[0]["factor_scores"]["pattern"]
            == "unknown-score"
        )


def test_duplicate_legacy_rows_remain_outer_only():
    rows = [
        {
            "stock_code": "2330",
            "stock_name": "台積電",
            "total_score": 82.35,
            "factor_scores": {},
            "selection_reason": "first row",
        },
        {
            "stock_code": "2330",
            "stock_name": "台積電",
            "total_score": 81.0,
            "factor_scores": {},
            "selection_reason": "duplicate row",
        },
    ]

    snapshot = _snapshot(rows)

    assert snapshot.recommendations == rows
    assert snapshot.canonical_execution is None


@pytest.mark.parametrize(
    "rows",
    [
        [{"stock_code": 2330, "total_score": 82.35}],
        [{"stock_code": "   ", "total_score": 82.35}],
        [{"total_score": 82.35}],
        [["not-a-mapping-row"]],
        [{"stock_code": "2330", "factor_scores": [70, 60]}],
        [{"stock_code": "2330", "stock_name": 2330}],
        [{"stock_code": "2330", "selection_reason": ["not", "text"]}],
    ],
)
def test_unmappable_legacy_rows_are_preserved_without_rehydration(rows: list[Any]):
    snapshot = _snapshot(rows)

    assert snapshot.recommendations == rows
    assert snapshot.canonical_execution is None


def test_provider_error_keeps_the_existing_replay_error_behavior():
    def provider(
        data: pd.DataFrame, config: dict[str, Any], top_n: int
    ) -> list[dict[str, Any]]:
        raise RuntimeError("synthetic provider error")

    history = pd.DataFrame(
        {"日期": [20260901], "證券代號": ["2330"]}
    )
    with pytest.raises(RuntimeError, match="synthetic provider error"):
        RecommendationReplayService(provider).run_snapshot(
            as_of_date="2026-09-01",
            profile_id="profile-r017-test-v1",
            config={},
            history=history,
            universe=None,
            top_n=1,
        )
