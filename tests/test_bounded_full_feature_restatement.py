from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import json

import pytest

from data_module.bounded_allocation_full_feature_restatement import (
    PRICE_FAMILY,
    QUALITY_FEATURE_IDS,
    TECHNICAL_FEATURE_IDS,
    BoundedFeatureRestatementError,
    _RestatementStats,
    _price_quality_stats,
    _source_decimal,
)
from data_module.bounded_allocation_label_restatement import (
    _canonical_json,
    _sha256_json,
)
from ml_module.allocation_contracts import (
    AllocationWeightContract,
    CausalPortfolioState,
    PITFeatureValue,
    PortfolioMLDatasetRow,
)
from ml_module.bounded_restated_research_consumer import (
    BoundedRestatedResearchError,
    _parse_feature,
    _parse_labels,
)


def test_grouped_ohlc_parser_only_strips_valid_grouping() -> None:
    parsed, grouped = _source_decimal(
        "1,005.00", symbol="2330", date="20240704", field="收盤價"
    )
    assert parsed == Decimal("1005.00")
    assert grouped is True

    assert _source_decimal(
        None, symbol="1101", date="20140102", field="開盤價"
    ) == (None, False)
    assert _source_decimal(
        "--", symbol="1101", date="20140102", field="開盤價"
    ) == (None, False)

    with pytest.raises(BoundedFeatureRestatementError, match="invalid OHLC"):
        _source_decimal(
            "1,00.00", symbol="2330", date="20240704", field="收盤價"
        )


def test_price_quality_metrics_recount_causal_warmup_missingness() -> None:
    features = []
    definitions = {}
    for feature_id in (
        *sorted(TECHNICAL_FEATURE_IDS),
        *[f"legacy_{index}" for index in range(21)],
    ):
        is_indicator = feature_id in TECHNICAL_FEATURE_IDS
        value_int = None if feature_id == "technical_indicators.MA60" else 10
        features.append(
            {
                "feature_id": feature_id,
                "family_id": PRICE_FAMILY,
                "source_id": (
                    "derived:causal_technical_indicators"
                    if is_indicator
                    else "sqlite.daily_prices"
                ),
                "value_int": value_int,
                "observed": value_int is not None,
                "available_at": "2026-09-21T14:30:00+08:00",
                "event_at": "2026-09-21T14:30:00+08:00",
                "quality_blocked_mask": False,
            }
        )
        definitions[feature_id] = {"stale_after_days": 7}

    metrics = _price_quality_stats(
        features=features,
        definitions=definitions,
        decision_date="2026-09-22",
    )
    assert metrics == {
        "coverage_bp": 40 * 10_000 // 41,
        "missing_count": 1,
        "stale_count": 0,
        "quality_blocked_count": 0,
        "max_available_lag_days": 1,
    }


def test_research_parser_keeps_event_and_actual_revision_clocks_separate() -> None:
    revision = "2026-09-23T04:47:20+00:00"
    feature = {
        "feature_id": "technical_indicators.MA60",
        "family_id": PRICE_FAMILY,
        "source_id": "derived:causal_technical_indicators",
        "value_int": 123456,
        "scale": 10_000,
        "event_at": "2026-09-21T14:30:00+08:00",
        "available_at": revision,
        "revision_id": "sha256:" + "1" * 64,
        "quality": "estimated",
        "content_hash": "sha256:" + "2" * 64,
        "observed": True,
        "event_time_semantics": "realized_observation",
    }
    parsed = _parse_feature(
        feature,
        decision_clock=datetime.fromisoformat("2026-09-22T08:30:00+08:00"),
        revision_clock=datetime.fromisoformat(revision),
        definitions={
            "technical_indicators.MA60": {
                "feature_id": "technical_indicators.MA60",
                "scale": 10_000,
                "source_id": "derived:causal_technical_indicators",
            }
        },
        source_hash_by_id={
            "derived:causal_technical_indicators": "sha256:" + "3" * 64
        },
    )
    assert parsed.event_at == feature["event_at"]
    assert parsed.available_at == revision

    with pytest.raises(
        BoundedRestatedResearchError, match="unapproved future feature availability"
    ):
        _parse_feature(
            {**feature, "feature_id": "daily_prices.收盤價"},
            decision_clock=datetime.fromisoformat("2026-09-22T08:30:00+08:00"),
            revision_clock=datetime.fromisoformat(revision),
            definitions={},
            source_hash_by_id={
                "derived:causal_technical_indicators": "sha256:" + "3" * 64
            },
        )


@pytest.mark.parametrize(
    ("feature_id", "family_id", "source_id", "revision_id", "value_int", "quality", "observed"),
    [
        (
            "data_quality.market_sector_cross_section.coverage_bp",
            "data_quality",
            "derived:feature_quality",
            "derived:data-quality-v1",
            5454,
            "observed",
            True,
        ),
        (
            "industry_indices.收盤指數",
            "market_sector_cross_section",
            "sqlite.industry_indices",
            "missing:not_observed_as_of_decision",
            None,
            "missing",
            False,
        ),
    ],
)
def test_unchanged_features_preserve_non_hash_revision_ids(
    feature_id: str,
    family_id: str,
    source_id: str,
    revision_id: str,
    value_int: int | None,
    quality: str,
    observed: bool,
) -> None:
    parsed = _parse_feature(
        {
            "feature_id": feature_id,
            "family_id": family_id,
            "source_id": source_id,
            "value_int": value_int,
            "scale": 1 if value_int is not None else 10_000,
            "event_at": "2014-01-02",
            "available_at": "2014-01-03T08:30:00+08:00",
            "revision_id": revision_id,
            "quality": quality,
            "content_hash": "sha256:" + "2" * 64,
            "observed": observed,
            "event_time_semantics": "realized_observation",
        },
        decision_clock=datetime.fromisoformat("2014-01-03T08:30:00+08:00"),
        revision_clock=datetime.fromisoformat("2026-09-23T04:47:20+00:00"),
        definitions={},
        source_hash_by_id={source_id: "sha256:" + "3" * 64},
    )

    assert parsed.revision_id == revision_id


def test_recomputed_feature_revision_id_must_remain_sha256() -> None:
    with pytest.raises(BoundedRestatedResearchError, match="feature.revision_id must be a sha256 digest"):
        _parse_feature(
            {
                "feature_id": "technical_indicators.MA60",
                "family_id": PRICE_FAMILY,
                "source_id": "derived:causal_technical_indicators",
                "value_int": 123456,
                "scale": 10_000,
                "event_at": "2026-09-21T14:30:00+08:00",
                "available_at": "2026-09-23T04:47:20+00:00",
                "revision_id": "derived:old-revision",
                "quality": "estimated",
                "content_hash": "sha256:" + "2" * 64,
                "observed": True,
                "event_time_semantics": "realized_observation",
            },
            decision_clock=datetime.fromisoformat("2026-09-22T08:30:00+08:00"),
            revision_clock=datetime.fromisoformat("2026-09-23T04:47:20+00:00"),
            definitions={
                "technical_indicators.MA60": {
                    "feature_id": "technical_indicators.MA60",
                    "scale": 10_000,
                    "source_id": "derived:causal_technical_indicators",
                }
            },
            source_hash_by_id={
                "derived:causal_technical_indicators": "sha256:" + "3" * 64
            },
        )


def test_frozen_pit_row_rejects_actual_late_feature_availability() -> None:
    revision = "2026-09-23T04:47:20+00:00"
    source_id = "derived:causal_technical_indicators"
    feature = PITFeatureValue(
        feature_id="technical_indicators.MA60",
        family_id=PRICE_FAMILY,
        source_id=source_id,
        value_int=123456,
        scale=10_000,
        event_at="2026-09-21T14:30:00+08:00",
        available_at=revision,
        revision_id="sha256:" + "1" * 64,
        quality="estimated",
        content_hash="sha256:" + "2" * 64,
        observed=True,
    )
    state = CausalPortfolioState.create(
        as_of_date="2026-09-21",
        weights=AllocationWeightContract(positions_bp=(), cash_bp=10_000),
        weekly_turnover_used_bp=0,
    )
    with pytest.raises(
        ValueError, match="feature available_at must not exceed decision_at"
    ):
        PortfolioMLDatasetRow(
            row_id="row:2026-09-22:1101",
            decision_at="2026-09-22T08:30:00+08:00",
            symbol="1101",
            features=(feature,),
            missing_family_ids=(),
            portfolio_state=state,
            dataset_identity_hash="sha256:" + "4" * 64,
            feature_registry_hash="sha256:" + "5" * 64,
            source_manifest_hashes=(
                (source_id, "sha256:" + "3" * 64),
            ),
            targets=None,
        )


def test_research_label_retains_maturity_and_actual_revision_clock() -> None:
    maturity = "2026-05-20T14:30:00+08:00"
    revision = "2026-09-23T04:47:20+00:00"
    label = {
        "horizon_trading_days": 60,
        "horizon_end_date": "2026-05-20",
        "available_at": maturity,
        "benchmark_excess_return_bp": -2555,
        "sector_excess_return_bp": None,
        "sector_excess_observed": False,
        "sector_excess_missing_reason": "pit_sector_membership_unavailable_at_decision",
        "downside_observed": True,
        "mae_bp": 1250,
        "mfe_bp": 410,
        "realized_volatility_bp": 169,
        "max_drawdown_bp": 1507,
        "tail_loss_bp": 230,
        "fill_feasible_observed": True,
    }
    parsed = _parse_labels(
        [label],
        [
            {
                "horizon_trading_days": 60,
                "event_maturity_available_at": maturity,
                "revision_available_at": revision,
                "restated": True,
            }
        ],
        revision_observed_at=revision,
        revision_clock=datetime.fromisoformat(revision),
    )[0]
    assert parsed.available_at == maturity
    assert parsed.revision_available_at == revision
    assert parsed.restated is True

    with pytest.raises(BoundedRestatedResearchError, match="revision predates"):
        _parse_labels(
            [label],
            [
                {
                    "horizon_trading_days": 60,
                    "event_maturity_available_at": maturity,
                    "revision_available_at": "2026-05-20T14:29:00+08:00",
                    "restated": True,
                }
            ],
            revision_observed_at=revision,
            revision_clock=datetime.fromisoformat(revision),
        )


def test_quality_slots_are_recomputed_not_missing_from_feature_abi() -> None:
    assert len(QUALITY_FEATURE_IDS) == 5


def test_quality_counter_keys_are_json_stable_before_manifest_hashing() -> None:
    stats = _RestatementStats(TECHNICAL_FEATURE_IDS)
    stats.quality_values["missing_count"].update({2: 4, 12: 9, 41: 3})

    payload = {"feature_restate_counts": stats.payload()}
    encoded = _canonical_json(payload)
    decoded = json.loads(encoded)

    quality_counts = payload["feature_restate_counts"][
        "quality_metric_value_counts"
    ]["missing_count"]
    assert quality_counts == {"12": 9, "2": 4, "41": 3}
    assert _sha256_json(payload) == _sha256_json(decoded)
