"""官方來源修訂有獨立研究範圍，舊來源 gate 保持嚴格。"""
from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest

from data_module.bounded_allocation_label_restatement import BoundedRestatementError, _scaled_bar
from data_module.bounded_official_market_restatement import (
    MARKET_RAW_IDS, MARKET_SOURCE_ID, _RUN02_CANDIDATE_SNAPSHOT_SHA256,
    _decision_day, _rebuild_labels, _require_candidate_profile_for_snapshot,
    OFFICIAL_RESTATEMENT_SCHEMA, RESEARCH_PUBLICATION_SCHEMA, _sha256_json,
    official_feature_registry, validate_official_bounded_manifest,
)
from ml_module.bounded_restated_research_consumer import _parse_feature, _parse_labels, _official_purged_train_end


def _label(horizon=5):
    return {"horizon_trading_days": horizon, "horizon_end_date": "2015-01-02", "available_at": "2015-01-02T14:30:00+08:00",
        "benchmark_excess_return_bp": 0, "sector_excess_return_bp": None, "sector_excess_observed": False,
        "sector_excess_missing_reason": "pit_sector_membership_unavailable_at_decision", "downside_observed": False,
        "mae_bp": 0, "mfe_bp": 0, "realized_volatility_bp": 0, "max_drawdown_bp": 0, "tail_loss_bp": 0, "fill_feasible_observed": True}


def test_bounded_label_uses_real_open_and_corrected_saturday_calendar():
    days = ["20141226", "20141227", "20141229", "20141230", "20141231"]
    market = {day: _scaled_bar({"開盤價": "100", "最高價": "112", "最低價": "99", "收盤價": "110"}) for day in days}
    prices = {day: _scaled_bar({"開盤價": "100", "最高價": "106", "最低價": "99", "收盤價": "105"}) for day in days}
    sample = {"row": {"decision_at": "2014-12-26T08:30:00+08:00", "symbol": "2330"}, "horizon_labels": [_label()]}
    result = _rebuild_labels(sample, days, {day: i for i, day in enumerate(days)}, market, prices)[0]
    assert result["benchmark_excess_return_bp"] == -580
    assert result["horizon_end_date"] == "2014-12-31"
    assert result["available_at"] == "2014-12-31T14:30:00+08:00"
    assert result["downside_observed"] is True
    with pytest.raises(BoundedRestatementError, match="corporate_action"):
        _rebuild_labels(sample, days, {day: i for i, day in enumerate(days)}, market, prices, ("2014-12-31",))
    del prices["20141227"]
    with pytest.raises(BoundedRestatementError, match="incomplete stock path"):
        _rebuild_labels(sample, days, {day: i for i, day in enumerate(days)}, market, prices)


def test_candidate_label_and_market_decisions_use_equivalent_taipei_local_day():
    days = ["20241106", "20241107", "20241108", "20241111", "20241112"]
    market = {day: _scaled_bar({"開盤價": "100", "最高價": "112", "最低價": "99", "收盤價": "110"}) for day in days}
    prices = {day: _scaled_bar({"開盤價": "100", "最高價": "106", "最低價": "99", "收盤價": "105"}) for day in days}
    index = {day: i for i, day in enumerate(days)}
    labels = []
    for decision_at in ("2024-11-05T17:00:00+00:00", "2024-11-06T01:00:00+08:00"):
        sample = {"row": {"decision_at": decision_at, "symbol": "2330"}, "horizon_labels": [_label()]}
        labels.append(_rebuild_labels(sample, days, index, market, prices, taipei_local_decision=True)[0])
        assert _decision_day(decision_at, taipei_local=True).isoformat() == "2024-11-06"
    assert labels[0] == labels[1]
    assert labels[0]["horizon_end_date"] == "2024-11-12"


def test_run02_snapshot_requires_candidate_daily_source_profile_but_legacy_hash_does_not():
    with pytest.raises(ValueError, match="requires the verified daily-source profile"):
        _require_candidate_profile_for_snapshot(
            _RUN02_CANDIDATE_SNAPSHOT_SHA256,
            candidate_stock=False,
        )
    _require_candidate_profile_for_snapshot(
        _RUN02_CANDIDATE_SNAPSHOT_SHA256,
        candidate_stock=True,
    )
    _require_candidate_profile_for_snapshot(
        "sha256:" + "1" * 64,
        candidate_stock=False,
    )


def test_consumer_rejects_run02_publication_with_removed_candidate_profile_before_parent_read():
    identity_keys = (
        "schema_version market_source_contract fold_profile started_at revision_observed_at "
        "parent_manifest_path parent_manifest_file_sha256 parent_training_as_of "
        "source_snapshot_sha256 source_snapshot_path official_market_manifest_path "
        "official_market_manifest_file_sha256 producer_code_root computation_source_hashes "
        "selection_policy corporate_action_manifest_path corporate_action_manifest_file_sha256"
    ).split()
    identity = {key: "unused-before-source-guard" for key in identity_keys}
    identity["source_snapshot_sha256"] = _RUN02_CANDIDATE_SNAPSHOT_SHA256
    manifest = {
        "schema_version": RESEARCH_PUBLICATION_SCHEMA,
        "research_only": True,
        "production_alpha_bp": 0,
        "dataset_temporality": "restated_research",
        "dataset_identity_hash": _sha256_json(identity),
        "restatement": {"schema_version": OFFICIAL_RESTATEMENT_SCHEMA, "identity_payload": identity},
        **{key: False for key in (
            "historical_pit", "formal_oos_allowed", "production_action_allowed",
            "promotion_eligible", "direct_training_input", "formal_consumer_compatible",
        )},
    }
    manifest["manifest_hash"] = _sha256_json(manifest)
    with pytest.raises(ValueError, match="requires the verified daily-source profile"):
        validate_official_bounded_manifest(manifest)


@pytest.mark.parametrize("horizon", [5, 10, 20, 60])
def test_official_labels_keep_actual_revision_without_relaxing_legacy_scope(horizon):
    label = _label(horizon)
    revision = "2026-09-23T04:47:20+00:00"
    clocks = [{"horizon_trading_days": horizon, "event_maturity_available_at": label["available_at"],
               "revision_available_at": revision, "restated": True}]
    args = dict(revision_observed_at=revision, revision_clock=datetime.fromisoformat(revision))
    result = _parse_labels([label], clocks, official_market=True, **args)[0]
    assert result.revision_available_at == revision and result.available_at == label["available_at"]
    if horizon != 60:
        with pytest.raises(ValueError, match="only corrected H60"):
            _parse_labels([label], clocks, **args)
    clocks[0].update(restated=False, revision_available_at=label["available_at"])
    with pytest.raises(ValueError, match="actual revision"):
        _parse_labels([label], clocks, official_market=True, **args)


def _feature(name, source, clock):
    return {"feature_id": name, "family_id": "market_sector_cross_section" if name.startswith("market_indices.") else "price_liquidity_technical",
        "source_id": source, "value_int": 12340000, "scale": 10000, "event_at": "2014-12-25T14:30:00+08:00", "available_at": clock,
        "revision_id": "sha256:" + "1" * 64, "quality": "observed", "content_hash": "sha256:" + "2" * 64,
        "observed": True, "event_time_semantics": "realized_observation"}


def test_stock_clock_is_preserved_and_official_market_clock_cannot_be_backdated():
    parent, current = "2026-09-23T04:00:00+00:00", "2026-09-23T05:00:00+00:00"
    technical_source = "derived:causal_technical_indicators"
    stock = _feature("technical_indicators.MA60", technical_source, parent)
    market = _feature("market_indices.收盤價", MARKET_SOURCE_ID, current)
    args = dict(decision_clock=datetime.fromisoformat("2014-12-26T08:30:00+08:00"), revision_clock=datetime.fromisoformat(current),
        definitions={item["feature_id"]: {"scale": 10000, "source_id": item["source_id"]} for item in (stock, market)},
        source_hash_by_id={technical_source: "sha256:" + "3" * 64, MARKET_SOURCE_ID: "sha256:" + "4" * 64},
        official_market=True, stock_revision_clock=datetime.fromisoformat(parent))
    assert _parse_feature(stock, **args).available_at == parent
    assert _parse_feature(market, **args).available_at == current
    market["available_at"] = parent
    with pytest.raises(ValueError, match="actual revision"):
        _parse_feature(market, **args)
    stock["available_at"] = current
    with pytest.raises(ValueError, match="actual revision"):
        _parse_feature(stock, **args)


def test_registry_changes_only_market_source_definitions_and_keeps_scales():
    features = [{"feature_id": name, "source_id": "sqlite.market_indices", "table_name": "market_indices", "record_hash": "sha256:" + "a" * 64, "scale": 10000}
                for name in sorted(MARKET_RAW_IDS)]
    other = {"feature_id": "technical_indicators.MA60", "source_id": "derived:causal_technical_indicators", "scale": 10000}
    parent = {"feature_registry": {"features": [*features, other]}}
    original = deepcopy(parent)
    registry = official_feature_registry(parent, "sha256:" + "b" * 64)
    assert parent == original
    assert other in registry["features"]
    changed = [item for item in registry["features"] if item["feature_id"] in MARKET_RAW_IDS]
    assert len(changed) == 8 and all(item["scale"] == 10000 and item["source_id"] == MARKET_SOURCE_ID for item in changed)


def test_excluding_missing_price_rows_makes_purge_stricter_without_changing_test_window():
    dates = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(200)]
    retained = dates[:80] + dates[100:]
    test_start = dates[150]
    cutoff = _official_purged_train_end(retained, test_start=test_start, declared_train_end=dates[89], purge_days=60)
    assert cutoff == dates[69]
    assert retained.index(test_start) - retained.index(cutoff) - 1 == 60
    assert _official_purged_train_end(retained, test_start=test_start, declared_train_end=dates[30], purge_days=60) == dates[30]
    with pytest.raises(ValueError, match="too short"):
        _official_purged_train_end(retained, test_start=dates[20], declared_train_end=dates[0], purge_days=60)
