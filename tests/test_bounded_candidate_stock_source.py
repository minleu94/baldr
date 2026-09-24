from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from analysis_module.technical_analysis.technical_indicators import CAUSAL_INDICATOR_COLUMNS
from data_module.bounded_candidate_stock_source import (
    CANDIDATE_RAW_FIELD_MAP,
    CANDIDATE_STOCK_FEATURE_IDS,
    CandidateStockSourceIndex,
    _candidate_price_quality_stats,
    _taipei_decision_date,
    candidate_stock_feature_registry,
    rebuild_candidate_stock_features,
)
from data_module.bounded_allocation_full_feature_restatement import (
    QUALITY_FEATURE_IDS,
    QUALITY_SOURCE_ID,
    TECHNICAL_FEATURE_IDS,
    TECHNICAL_SOURCE_ID,
)
from data_module.bounded_official_market_restatement import MARKET_FEATURE_IDS
from data_module.ml_restatement_research_dataset import expected_feature_contract
from ml_module.bounded_restated_research_consumer import (
    BoundedRestatedResearchError,
    _parse_feature,
)


def _feature_contract():
    feature_ids, scales = expected_feature_contract()
    definitions = {}
    features = []
    for feature_id, scale in zip(feature_ids, scales, strict=True):
        if feature_id.startswith("data_quality."):
            family_id = "data_quality"
            source_id = QUALITY_SOURCE_ID if feature_id in QUALITY_FEATURE_IDS else "derived:market_quality"
        elif feature_id.startswith("market_indices."):
            family_id = "market_sector_cross_section"
            source_id = "sqlite.market_indices"
        elif feature_id.startswith("industry_indices."):
            family_id = "market_sector_cross_section"
            source_id = "sqlite.industry_indices"
        else:
            family_id = "price_liquidity_technical"
            if feature_id in CANDIDATE_RAW_FIELD_MAP:
                source_id = "sqlite.technical_indicators" if feature_id.startswith("technical_indicators.") else "sqlite.daily_prices"
            else:
                source_id = TECHNICAL_SOURCE_ID if feature_id in TECHNICAL_FEATURE_IDS else "sqlite.technical_indicators"
        definition = {
            "feature_id": feature_id,
            "family_id": family_id,
            "source_id": source_id,
            "table_name": source_id.split(".")[-1],
            "record_hash": "sha256:" + "a" * 64,
            "scale": scale,
            "stale_after_days": 7,
        }
        definitions[feature_id] = definition
        features.append({
            "feature_id": feature_id,
            "family_id": family_id,
            "source_id": source_id,
            "value_int": 11,
            "scale": scale,
            "event_at": "2024-11-04T14:30:00+08:00",
            "available_at": "2024-11-04T14:30:00+08:00",
            "revision_id": "sha256:" + "b" * 64,
            "quality": "observed",
            "content_hash": "sha256:" + "c" * 64,
            "observed": True,
            "event_time_semantics": "realized_observation",
        })
    return features, definitions


def _source_index() -> CandidateStockSourceIndex:
    profile = SimpleNamespace(profile_file_sha256="sha256:" + "d" * 64)
    fields = set(CANDIDATE_RAW_FIELD_MAP.values()) | {"開盤價", "最高價", "最低價", "收盤價"}
    row = {field: "10.25" for field in fields}
    row.update({
        "開盤價": "10",
        "最高價": "11",
        "最低價": "9.5",
        "收盤價": "10.5",
        "最後揭示買量": None,
        "涨跌": "-",
        "漲跌(+/-)": "+",
    })
    row.update(date_key="20241105")
    newer = {**row, "date_key": "20241106", "收盤價": "20", "最後揭示買量": "3"}
    latest = {**row, "date_key": "20241109", "收盤價": "12.5"}
    indicator_values = {column: 12345 for column in CAUSAL_INDICATOR_COLUMNS}
    return CandidateStockSourceIndex(
        profile=profile,  # type: ignore[arg-type]
        profile_reference={"path": "candidate.json", "file_sha256": profile.profile_file_sha256},
        snapshot_path=__import__("pathlib").Path("snapshot.sqlite"),
        snapshot_sha256="sha256:" + "e" * 64,
        revision_observed_at="2026-09-23T20:00:00+00:00",
        bridge_payload={},
        bridge_hash="sha256:" + "f" * 64,
        daily_rows_by_symbol={"2330": [row, newer, latest]},
        date_keys_by_symbol={"2330": ["20241105", "20241106", "20241109"]},
        indicator_values_by_symbol_date={
            "2330": {"20241105": indicator_values, "20241106": indicator_values, "20241109": indicator_values}
        },
        audit={},
    )


def test_candidate_rebuild_uses_taipei_t_minus_one_and_preserves_daily_nulls():
    features, definitions = _feature_contract()
    source = _source_index()
    rebuilt = rebuild_candidate_stock_features(
        source=source,
        features=features,
        row_id="2330:2024-11-06",
        symbol="2330",
        # 17:00 UTC is 01:00 the next day in Taipei.
        decision_at="2024-11-05T17:00:00+00:00",
        definitions=definitions,
        identity_hash="sha256:" + "1" * 64,
    )
    by_id = {feature["feature_id"]: feature for feature in rebuilt}
    assert len(rebuilt) == 62
    assert {feature_id for feature_id in by_id if feature_id in CANDIDATE_STOCK_FEATURE_IDS} == CANDIDATE_STOCK_FEATURE_IDS
    assert by_id["daily_prices.收盤價"]["value_int"] == 105000
    assert by_id["daily_prices.收盤價"]["event_at"] == "2024-11-05T14:30:00+08:00"
    assert by_id["daily_prices.收盤價"]["available_at"] == source.revision_observed_at
    assert by_id["daily_prices.最後揭示買量"]["value_int"] is None
    assert by_id["technical_indicators.最後揭示買量"]["value_int"] is None
    assert by_id["technical_indicators.涨跌"]["value_int"] is None
    assert by_id["technical_indicators.漲跌(+/-)"]["value_int"] is None
    assert by_id["technical_indicators.MA5"]["value_int"] == 12345
    assert by_id["data_quality.price_liquidity_technical.max_available_lag_days"]["value_int"] == 1
    assert by_id["data_quality.price_liquidity_technical.missing_count"]["value_int"] == 4
    assert by_id["data_quality.price_liquidity_technical.quality_blocked_count"]["value_int"] == 0


def test_candidate_quality_uses_event_day_instead_of_late_revision_availability():
    features, definitions = _feature_contract()
    price_definitions = {
        feature_id: definition
        for feature_id, definition in definitions.items()
        if definition["family_id"] == "price_liquidity_technical"
    }
    for feature in features:
        if feature["feature_id"] not in price_definitions:
            continue
        feature["event_at"] = "2024-11-05T14:30:00+08:00"
        feature["available_at"] = "2026-09-23T20:00:00+00:00"
    stats = _candidate_price_quality_stats(
        features=features,
        definitions=price_definitions,
        decision_date=_taipei_decision_date("2024-11-05T17:00:00+00:00"),
    )
    assert stats["max_available_lag_days"] == 1
    assert stats["stale_count"] == 0


@pytest.mark.parametrize(
    ("decision_at", "expected_value", "expected_stale_count"),
    [
        ("2024-11-15T17:00:00+00:00", 125000, 0),  # exactly seven Taipei calendar days
        ("2024-11-16T17:00:00+00:00", None, 41),  # eight days is stale
    ],
)
def test_candidate_preserves_original_seven_day_freshness_boundary(
    decision_at, expected_value, expected_stale_count
):
    features, definitions = _feature_contract()
    rebuilt = rebuild_candidate_stock_features(
        source=_source_index(),
        features=features,
        row_id="2330:freshness-boundary",
        symbol="2330",
        decision_at=decision_at,
        definitions=definitions,
        identity_hash="sha256:" + "1" * 64,
    )
    by_id = {feature["feature_id"]: feature for feature in rebuilt}
    assert by_id["daily_prices.收盤價"]["value_int"] == expected_value
    assert by_id["data_quality.price_liquidity_technical.stale_count"]["value_int"] == expected_stale_count
    if expected_value is None:
        assert by_id["technical_indicators.MA5"]["value_int"] is None
        assert by_id["data_quality.price_liquidity_technical.missing_count"]["value_int"] == 41
        assert by_id["data_quality.price_liquidity_technical.coverage_bp"]["value_int"] == 0
    else:
        assert by_id["technical_indicators.MA5"]["value_int"] == 12345


@pytest.mark.parametrize("source_close", ["0", "invalid"])
def test_candidate_preserves_original_positive_price_and_invalid_numeric_gate(source_close):
    source = _source_index()
    source.daily_rows_by_symbol["2330"][0]["收盤價"] = source_close
    features, definitions = _feature_contract()
    rebuilt = rebuild_candidate_stock_features(
        source=source,
        features=features,
        row_id="2330:blocked-price",
        symbol="2330",
        decision_at="2024-11-05T17:00:00+00:00",
        definitions=definitions,
        identity_hash="sha256:" + "1" * 64,
    )
    by_id = {feature["feature_id"]: feature for feature in rebuilt}
    assert by_id["daily_prices.收盤價"]["value_int"] is None
    assert by_id["data_quality.price_liquidity_technical.quality_blocked_count"]["value_int"] == 1


def test_candidate_decision_dates_require_timezone_and_convert_to_taipei():
    assert _taipei_decision_date("2024-11-05T17:00:00+00:00").isoformat() == "2024-11-06"
    with pytest.raises(ValueError, match="timezone"):
        _taipei_decision_date("2024-11-06T08:30:00")


def test_candidate_registry_explicitly_transitions_eight_aliases_to_daily_prices():
    features, _definitions = _feature_contract()
    registry = {"features": [
        {key: value for key, value in feature.items() if key in {"feature_id", "source_id", "table_name", "record_hash", "scale"}}
        for feature in features
    ]}
    converted = candidate_stock_feature_registry(
        registry,
        profile_sha256="sha256:" + "d" * 64,
        bridge_hash="sha256:" + "f" * 64,
    )
    by_id = {item["feature_id"]: item for item in converted["features"]}
    for feature_id in (
        "technical_indicators.最後揭示買價",
        "technical_indicators.最後揭示買量",
        "technical_indicators.最後揭示賣價",
        "technical_indicators.最後揭示賣量",
        "technical_indicators.本益比",
        "technical_indicators.涨跌",
        "technical_indicators.漲跌(+/-)",
        "technical_indicators.漲跌價差",
    ):
        assert by_id[feature_id]["source_id"] == "sqlite.daily_prices"
        assert by_id[feature_id]["table_name"] == "daily_prices"
        assert by_id[feature_id]["scale"] == next(item["scale"] for item in registry["features"] if item["feature_id"] == feature_id)
    assert registry["features"] != converted["features"]


def _future_candidate_feature(*, source_id="sqlite.daily_prices", available_at="2026-09-23T20:00:00+00:00"):
    return {
        "feature_id": "technical_indicators.最後揭示買量",
        "family_id": "price_liquidity_technical",
        "source_id": source_id,
        "value_int": None,
        "scale": 1,
        "event_at": "2024-11-05T14:30:00+08:00",
        "available_at": available_at,
        "revision_id": "sha256:" + "2" * 64,
        "quality": "missing",
        "content_hash": "sha256:" + "3" * 64,
        "observed": False,
        "event_time_semantics": "realized_observation",
    }


def test_consumer_allows_future_raw_alias_only_for_candidate_transition_and_real_clock():
    decision = datetime.fromisoformat("2024-11-06T08:30:00+08:00")
    revision = datetime.fromisoformat("2026-09-23T20:00:00+00:00")
    feature = _future_candidate_feature()
    arguments = {
        "decision_clock": decision,
        "revision_clock": revision,
        "definitions": {
            feature["feature_id"]: {"scale": 1, "source_id": "sqlite.daily_prices"}
        },
        "source_hash_by_id": {"sqlite.daily_prices": "sha256:" + "4" * 64},
        "official_market": True,
        "candidate_stock_source": True,
        "stock_revision_clock": revision,
    }
    parsed = _parse_feature(feature, **arguments)
    assert parsed.value_int is None and parsed.available_at == revision.isoformat()

    with pytest.raises(BoundedRestatedResearchError, match="unapproved future"):
        _parse_feature(feature, **{**arguments, "candidate_stock_source": False})
    with pytest.raises(BoundedRestatedResearchError, match="source transition"):
        _parse_feature(_future_candidate_feature(source_id="sqlite.technical_indicators"), **arguments)
    with pytest.raises(BoundedRestatedResearchError, match="actual rebuild clock"):
        _parse_feature(
            _future_candidate_feature(available_at="2026-09-23T19:59:00+00:00"),
            **arguments,
        )
