from __future__ import annotations

from datetime import date, timedelta
import json
import sqlite3

import pytest

from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.historical_feature_builder import HistoricalFeatureBuilder
from ml_module.recommendation_historical_replay import (
    RecommendationHistoricalReplayConfig,
    RecommendationHistoricalReplayService,
    _read_source_content_snapshot,
)


def _make_database(path, *, days: int = 150, symbols: tuple[str, ...] = ("AAA", "BBB")):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE daily_prices (
            日期 TEXT NOT NULL,
            證券代號 TEXT NOT NULL,
            成交股數 INTEGER,
            成交金額 INTEGER,
            開盤價 TEXT,
            最高價 TEXT,
            最低價 TEXT,
            收盤價 TEXT
        );
        CREATE TABLE technical_indicators (
            日期 TEXT NOT NULL,
            證券代號 TEXT NOT NULL,
            RSI TEXT,
            MACD TEXT,
            ADX TEXT
        );
        CREATE TABLE market_indices (
            日期 TEXT NOT NULL,
            收盤指數 TEXT,
            收盤價 TEXT
        );
        CREATE TABLE industry_indices (
            日期 TEXT NOT NULL,
            指數名稱 TEXT,
            收盤指數 TEXT
        );
        """
    )
    start = date(2014, 1, 1)
    for offset in range(days):
        current = (start + timedelta(days=offset)).strftime("%Y%m%d")
        connection.execute(
            "INSERT INTO market_indices VALUES (?, ?, ?)",
            (current, str(10_000 + offset), str(10_000 + offset)),
        )
        for symbol_index, symbol in enumerate(symbols):
            close = 100 + symbol_index * 20 + offset
            connection.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (current, symbol, 1000 + offset, close * 100, close, close + 1, close - 1, close),
            )
            connection.execute(
                "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?)",
                (current, symbol, "55", "1.5", "20"),
            )
    connection.commit()
    connection.close()


def _service(tmp_path):
    database = tmp_path / "replay.db"
    _make_database(database)
    return RecommendationHistoricalReplayService(
        MLHistoricalSnapshotProvider(database),
        feature_builder=HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY),
    )


def _add_verified_source_contract(database, *, decisions: tuple[date, ...], symbols: tuple[str, ...]) -> None:
    connection = sqlite3.connect(database)
    connection.execute("ALTER TABLE technical_indicators ADD COLUMN available_at TEXT")
    connection.execute("UPDATE technical_indicators SET available_at = 日期")
    connection.executescript(
        """
        CREATE TABLE corporate_action_adjustments (
            symbol TEXT NOT NULL,
            event_date TEXT NOT NULL,
            available_at TEXT NOT NULL,
            effective_from TEXT NOT NULL,
            adjustment_factor TEXT NOT NULL
        );
        CREATE TABLE recommendation_source_contract (
            component TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            source_table TEXT NOT NULL,
            status TEXT NOT NULL,
            coverage_start TEXT NOT NULL,
            coverage_end TEXT NOT NULL,
            available_at TEXT NOT NULL,
            evidence_hash TEXT NOT NULL,
            source_columns_json TEXT NOT NULL,
            publication_time_verified INTEGER NOT NULL,
            corporate_action_adjustment_verified INTEGER NOT NULL
        );
        CREATE TABLE evidence_events (
            event_id TEXT PRIMARY KEY,
            decision_date TEXT NOT NULL,
            symbol TEXT NOT NULL
        );
        CREATE TABLE evidence_outcomes (
            outcome_id INTEGER PRIMARY KEY,
            event_id TEXT NOT NULL,
            window_days INTEGER NOT NULL,
            outcome_status TEXT NOT NULL,
            outcome_price_date TEXT NOT NULL,
            liquidity_cost_bp INTEGER NOT NULL,
            calculated_at TEXT NOT NULL
        );
        """
    )
    for symbol in symbols:
        connection.execute(
            "INSERT INTO corporate_action_adjustments VALUES (?, ?, ?, ?, ?)",
            (symbol, "2014-01-01", "2014-01-01", "2014-01-01", "1"),
        )
        connection.execute(
            "INSERT INTO corporate_action_adjustments VALUES (?, ?, ?, ?, ?)",
            (symbol, "2014-05-20", "2014-05-20", "2014-05-20", "1"),
        )
    connection.commit()
    technical_content = _read_source_content_snapshot(
        database,
        component="technical",
        source_table="technical_indicators",
        symbols=symbols,
        history_start=date(2014, 1, 1),
        replay_end=date(2014, 5, 20),
    )
    corporate_content = _read_source_content_snapshot(
        database,
        component="corporate_actions",
        source_table="corporate_action_adjustments",
        symbols=symbols,
        history_start=date(2014, 1, 1),
        replay_end=date(2014, 5, 20),
    )
    connection.executemany(
        "INSERT INTO recommendation_source_contract VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            (
                "technical",
                "fixture-technical-v1",
                "technical_indicators",
                "accepted",
                "2014-01-01",
                "2014-12-31",
                "2014-01-01",
                technical_content["digest"],
                json.dumps(["日期", "證券代號", "RSI", "MACD", "ADX", "available_at"]),
                1,
                0,
            ),
            (
                "corporate_actions",
                "fixture-corporate-actions-v1",
                "corporate_action_adjustments",
                "accepted",
                "2014-01-01",
                "2014-12-31",
                "2014-01-01",
                corporate_content["digest"],
                json.dumps(
                    ["symbol", "event_date", "available_at", "effective_from", "adjustment_factor"]
                ),
                0,
                1,
            ),
        ),
    )
    outcome_id = 1
    for decision in decisions:
        label_date = decision + timedelta(days=20)
        for symbol in symbols:
            event_id = f"fixture-event-{decision.isoformat()}-{symbol}"
            connection.execute(
                "INSERT INTO evidence_events(event_id, decision_date, symbol) VALUES (?, ?, ?)",
                (event_id, decision.isoformat(), symbol),
            )
            connection.execute(
                "INSERT INTO evidence_outcomes(outcome_id, event_id, window_days, outcome_status, outcome_price_date, liquidity_cost_bp, calculated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    outcome_id,
                    event_id,
                    20,
                    "ready",
                    label_date.isoformat(),
                    25,
                    label_date.isoformat() + "T00:00:00+08:00",
                ),
            )
            outcome_id += 1
    connection.commit()
    connection.close()


def test_replay_is_bounded_causal_and_uses_absolute_labels(tmp_path):
    service = _service(tmp_path)
    result = service.build(
        RecommendationHistoricalReplayConfig(
            history_start_date="2014-01-01",
            replay_start_date="2014-03-15",
            replay_end_date="2014-05-20",
            symbols=("AAA", "BBB"),
            fixed_round_trip_cost_bp=35,
            max_decision_dates=3,
        )
    )

    assert len(result.decision_dates) == 3
    assert result.sample_count == 6
    assert result.coverage["max_decision_dates"] == 3
    assert result.formal_candidate_eligible is False
    assert "historical_replay_is_not_natural_forward_evidence" in result.candidate_blockers
    assert result.lookahead_checks["feature_snapshot_rows_strictly_before_decision"] is True
    assert result.lookahead_checks["future_label_dates_strictly_after_decision"] is True
    assert result.source_disclosures["constituents"]["point_in_time_history_provided"] is False
    assert result.source_disclosures["corporate_actions"]["source_available"] is False
    assert result.source_disclosures["technical"]["publication_time_verified"] is False
    assert result.source_disclosures["benchmark"]["role"].endswith("not a target")

    first = result.samples[0]
    assert first.feature_as_of_date < first.decision_date
    assert first.feature_available_date == first.decision_date
    assert first.label_end_date > first.decision_date
    assert first.label_available_date == first.label_end_date
    assert first.upside_label == int(first.stock_return_bp > 0)
    assert first.after_cost_profit_label is None
    assert first.observed_liquidity_cost_bp is None
    assert first.benchmark_return_bp != 0


def test_verified_source_contract_unlocks_only_traceable_cost_and_source_gates(tmp_path):
    database = tmp_path / "qualified-replay.db"
    _make_database(database)
    decisions = (date(2014, 3, 15), date(2014, 3, 16))
    _add_verified_source_contract(database, decisions=decisions, symbols=("AAA", "BBB"))
    service = RecommendationHistoricalReplayService(
        MLHistoricalSnapshotProvider(database),
        feature_builder=HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY),
    )

    result = service.build(
        RecommendationHistoricalReplayConfig(
            history_start_date="2014-01-01",
            replay_start_date="2014-03-15",
            replay_end_date="2014-05-20",
            symbols=("AAA", "BBB"),
            fixed_round_trip_cost_bp=35,
            max_decision_dates=2,
        )
    )

    assert result.source_disclosures["technical"]["publication_time_verified"] is True
    assert result.source_disclosures["corporate_actions"]["adjustment_verified"] is True
    assert result.source_disclosures["constituents"]["point_in_time_history_required"] is False
    assert result.source_disclosures["cost"]["coverage"] == "observed_complete"
    assert "technical_publication_time_unverified" not in result.candidate_blockers
    assert "corporate_action_source_or_adjustment_unverified" not in result.candidate_blockers
    assert "observed_liquidity_cost_missing_after_cost_target_unavailable" not in result.candidate_blockers
    assert "observed_liquidity_cost_partial_after_cost_target_unavailable" not in result.candidate_blockers
    assert all(sample.after_cost_profit_label is not None for sample in result.samples)
    assert all(
        sample.rule_after_cost_baseline_id == "after_cost_null_benchmark_50pct_v1"
        for sample in result.samples
    )


def test_source_contract_content_hash_mismatch_does_not_use_declared_verified_flag(tmp_path):
    database = tmp_path / "hash-mismatch.db"
    _make_database(database)
    _add_verified_source_contract(
        database,
        decisions=(date(2014, 3, 15), date(2014, 3, 16)),
        symbols=("AAA", "BBB"),
    )
    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE recommendation_source_contract SET evidence_hash = ? WHERE component = 'technical'",
        ("sha256:" + "f" * 64,),
    )
    connection.commit()
    connection.close()

    result = RecommendationHistoricalReplayService(
        MLHistoricalSnapshotProvider(database),
        feature_builder=HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY),
    ).build(
        RecommendationHistoricalReplayConfig(
            history_start_date="2014-01-01",
            replay_start_date="2014-03-15",
            replay_end_date="2014-05-20",
            symbols=("AAA", "BBB"),
            fixed_round_trip_cost_bp=35,
            max_decision_dates=2,
        )
    )

    assert result.source_disclosures["technical"]["publication_time_verified"] is False
    assert "source_content_hash_mismatch" in result.source_disclosures["technical"]["source_contract"]["reason"]
    assert "technical_publication_time_unverified" in result.candidate_blockers


def test_late_technical_row_is_rejected_even_when_content_hash_is_refreshed(tmp_path):
    database = tmp_path / "late-technical.db"
    _make_database(database)
    _add_verified_source_contract(
        database,
        decisions=(date(2014, 3, 15), date(2014, 3, 16)),
        symbols=("AAA", "BBB"),
    )
    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE technical_indicators SET available_at = ? WHERE 日期 = ? AND 證券代號 = ?",
        ("2014-03-16", "20140314", "AAA"),
    )
    connection.commit()
    connection.close()
    refreshed = _read_source_content_snapshot(
        database,
        component="technical",
        source_table="technical_indicators",
        symbols=("AAA", "BBB"),
        history_start=date(2014, 1, 1),
        replay_end=date(2014, 5, 20),
    )
    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE recommendation_source_contract SET evidence_hash = ? WHERE component = 'technical'",
        (refreshed["digest"],),
    )
    connection.commit()
    connection.close()

    result = RecommendationHistoricalReplayService(
        MLHistoricalSnapshotProvider(database),
        feature_builder=HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY),
    ).build(
        RecommendationHistoricalReplayConfig(
            history_start_date="2014-01-01",
            replay_start_date="2014-03-15",
            replay_end_date="2014-05-20",
            symbols=("AAA", "BBB"),
            fixed_round_trip_cost_bp=35,
            max_decision_dates=2,
        )
    )

    reason = result.source_disclosures["technical"]["source_contract"]["reason"]
    assert "technical_usage_available_after_decision:AAA:2014-03-14" in reason
    assert "technical_publication_time_unverified" in result.candidate_blockers


def test_unadjusted_corporate_action_excludes_affected_label_window(tmp_path):
    database = tmp_path / "corporate-action.db"
    _make_database(database)
    _add_verified_source_contract(
        database,
        decisions=(date(2014, 3, 15), date(2014, 3, 16)),
        symbols=("AAA", "BBB"),
    )
    connection = sqlite3.connect(database)
    connection.execute(
        "INSERT INTO corporate_action_adjustments VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2014-03-20", "2014-03-20", "2014-03-20", "1.2"),
    )
    connection.commit()
    connection.close()
    refreshed = _read_source_content_snapshot(
        database,
        component="corporate_actions",
        source_table="corporate_action_adjustments",
        symbols=("AAA", "BBB"),
        history_start=date(2014, 1, 1),
        replay_end=date(2014, 5, 20),
    )
    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE recommendation_source_contract SET evidence_hash = ? WHERE component = 'corporate_actions'",
        (refreshed["digest"],),
    )
    connection.commit()
    connection.close()

    result = RecommendationHistoricalReplayService(
        MLHistoricalSnapshotProvider(database),
        feature_builder=HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY),
    ).build(
        RecommendationHistoricalReplayConfig(
            history_start_date="2014-01-01",
            replay_start_date="2014-03-15",
            replay_end_date="2014-05-20",
            symbols=("AAA", "BBB"),
            fixed_round_trip_cost_bp=35,
            max_decision_dates=2,
        )
    )

    assert result.sample_count == 2
    assert "corporate_action_source_or_adjustment_unverified" in result.candidate_blockers
    assert "corporate_action_unadjusted_label_windows_excluded:2" in result.diagnostics
    assert result.source_disclosures["corporate_actions"]["adjustment_verified"] is False


def test_empty_corporate_action_source_is_not_coverage(tmp_path):
    database = tmp_path / "empty-corporate-action.db"
    _make_database(database)
    _add_verified_source_contract(
        database,
        decisions=(date(2014, 3, 15), date(2014, 3, 16)),
        symbols=("AAA", "BBB"),
    )
    connection = sqlite3.connect(database)
    connection.execute("DELETE FROM corporate_action_adjustments")
    connection.commit()
    connection.close()
    refreshed = _read_source_content_snapshot(
        database,
        component="corporate_actions",
        source_table="corporate_action_adjustments",
        symbols=("AAA", "BBB"),
        history_start=date(2014, 1, 1),
        replay_end=date(2014, 5, 20),
    )
    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE recommendation_source_contract SET evidence_hash = ? WHERE component = 'corporate_actions'",
        (refreshed["digest"],),
    )
    connection.commit()
    connection.close()

    result = RecommendationHistoricalReplayService(
        MLHistoricalSnapshotProvider(database),
        feature_builder=HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY),
    ).build(
        RecommendationHistoricalReplayConfig(
            history_start_date="2014-01-01",
            replay_start_date="2014-03-15",
            replay_end_date="2014-05-20",
            symbols=("AAA", "BBB"),
            fixed_round_trip_cost_bp=35,
            max_decision_dates=2,
        )
    )

    reason = result.source_disclosures["corporate_actions"]["source_contract"]["reason"]
    assert "source_content_rows_empty" in reason
    assert "source_content_symbol_coverage_missing:AAA,BBB" in reason
    assert "corporate_action_source_or_adjustment_unverified" in result.candidate_blockers


def test_replay_manifest_is_immutable_and_explicitly_research_only(tmp_path):
    service = _service(tmp_path)
    config = RecommendationHistoricalReplayConfig(
        history_start_date="2014-01-01",
        replay_start_date="2014-03-15",
        replay_end_date="2014-05-20",
        symbols=("AAA",),
        fixed_round_trip_cost_bp=50,
        max_decision_dates=2,
    )
    result = service.build(config)
    path = result.persist(tmp_path / "output")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["dataset_hash"] == result.dataset_hash
    assert payload["shadow_only"] is True
    assert payload["production_action_allowed"] is False
    assert payload["source_disclosures"]["cost"]["observed_liquidity_cost_source"] is None
    assert result.persist(tmp_path / "output") == path

    payload["diagnostics"] = ["tampered"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="immutable historical replay dataset conflict"):
        result.persist(tmp_path / "output")
