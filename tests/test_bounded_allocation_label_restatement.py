from __future__ import annotations

import copy

import pytest

from data_module.bounded_allocation_label_restatement import (
    BoundedRestatementError,
    PRICE_SCALE,
    _WriteStats,
    _recompute_label,
    _scaled_bar,
)


def _bar(open_value: int, high: int, low: int, close: int) -> dict[str, int]:
    return {
        "open_int": open_value * PRICE_SCALE,
        "open_scale": PRICE_SCALE,
        "high_int": high * PRICE_SCALE,
        "high_scale": PRICE_SCALE,
        "low_int": low * PRICE_SCALE,
        "low_scale": PRICE_SCALE,
        "close_int": close * PRICE_SCALE,
        "close_scale": PRICE_SCALE,
    }


def test_recompute_uses_only_the_matured_horizon_and_decimal_label_helpers() -> None:
    calendar = ["20260519", "20260520", "20260521", "20260522"]
    stock = {
        "20260519": _bar(100, 102, 99, 101),
        "20260520": _bar(101, 103, 100, 102),
        "20260521": _bar(102, 104, 101, 103),
        # A deliberately extreme suffix must not change the H3 outcome.
        "20260522": _bar(1, 20_000, 1, 19_000),
    }
    benchmark = {
        "20260519": _bar(100, 101, 99, 100),
        "20260520": _bar(100, 101, 99, 100),
        "20260521": _bar(100, 102, 99, 101),
    }

    label = _recompute_label(
        symbol="1101",
        decision_date="20260519",
        end_date="20260521",
        horizon=3,
        calendar=calendar,
        benchmark=benchmark,
        price_path=stock,
    )

    assert label == {
        "benchmark_excess_return_bp": 120,
        "downside_observed": False,
        "mae_bp": 100,
        "mfe_bp": 400,
        "realized_volatility_bp": 0,
        "max_drawdown_bp": 0,
        "tail_loss_bp": 0,
        "fill_feasible_observed": True,
    }


def test_recompute_rejects_horizon_end_that_does_not_match_calendar_length() -> None:
    with pytest.raises(BoundedRestatementError, match="calendar is inconsistent"):
        _recompute_label(
            symbol="1101",
            decision_date="20260519",
            end_date="20260521",
            horizon=2,
            calendar=["20260519", "20260520", "20260521"],
            benchmark={},
            price_path={},
        )


def test_scaled_bar_preserves_source_nulls() -> None:
    result = _scaled_bar(
        {
            "開盤價": "10.25",
            "最高價": None,
            "最低價": "10.10",
            "收盤價": "10.20",
        }
    )

    assert result == {
        "open_int": 102_500,
        "open_scale": PRICE_SCALE,
        "high_int": None,
        "high_scale": PRICE_SCALE,
        "low_int": 101_000,
        "low_scale": PRICE_SCALE,
        "close_int": 102_000,
        "close_scale": PRICE_SCALE,
    }


def test_scaled_bar_normalizes_grouped_prices_and_missing_sentinel() -> None:
    result = _scaled_bar(
        {
            "開盤價": "1,010.00",
            "最高價": "1,020.00",
            "最低價": "--",
            "收盤價": "1,015.00",
        }
    )

    assert result["open_int"] == 10_100_000
    assert result["open_scale"] == 10_000
    assert result["low_int"] is None
    assert result["low_scale"] == 10_000


def test_preservation_guard_covers_ids_features_masks_targets_and_state() -> None:
    sample = {
        "row": {
            "row_id": "row:20260519:1101",
            "features": [{"feature_id": "rsi", "value": 51}],
            "missing_family_ids": ["fret"],
            "targets": {
                "target_weights": {"positions_bp": [], "cash_bp": 10_000},
                "risky_budget_bp": 0,
            },
            "portfolio_state": {"cash_bp": 10_000, "holdings": []},
        },
        "horizon_labels": [{"horizon_trading_days": 60}],
    }
    stats = _WriteStats()
    stats.observe_sample(sample)

    transformed = copy.deepcopy(sample)
    transformed["row"]["dataset_identity_hash"] = "sha256:" + "a" * 64
    transformed["row"]["source_manifest_hashes"] = [["snapshot", "sha256:" + "b" * 64]]
    transformed["horizon_labels"][0]["mae_bp"] = 123
    stats.observe_after_sample(transformed)

    stats.assert_preserved()
    preservation = stats.preservation_payload()
    assert preservation["row_count_preserved"] == 1
    assert preservation["row_ids_sha256_before"] == preservation["row_ids_sha256_after"]
    assert preservation["features_and_masks_sha256_before"] == preservation[
        "features_and_masks_sha256_after"
    ]
    assert preservation["teacher_targets_sha256_before"] == preservation[
        "teacher_targets_sha256_after"
    ]
    assert preservation["portfolio_state_sha256_before"] == preservation[
        "portfolio_state_sha256_after"
    ]


def test_preservation_guard_fails_if_features_or_targets_change() -> None:
    sample = {
        "row": {
            "row_id": "row:20260519:1101",
            "features": [1],
            "missing_family_ids": [],
            "targets": {"target_weights": {"positions_bp": [], "cash_bp": 10_000}, "risky_budget_bp": 0},
            "portfolio_state": {"cash_bp": 10_000},
        }
    }
    stats = _WriteStats()
    stats.observe_sample(sample)
    changed = copy.deepcopy(sample)
    changed["row"]["features"] = [2]
    stats.observe_after_sample(changed)

    with pytest.raises(BoundedRestatementError, match="preservation check failed: features"):
        stats.assert_preserved()
