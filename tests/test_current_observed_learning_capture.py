from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scripts.scheduled.run_daily_recommendation_learning import (
    _current_observed_raw_cycle_discovery_problem,
    _current_observed_outcome_samples,
    _current_observed_capture_semantic_hash,
    _deduplicate_current_observed_samples,
    _cost_scenario_root_conflict,
    _is_rule_only_pointer_capture_lane_conflict,
    _read_current_observed_entry_prices,
    _current_observed_feature_snapshot_for_learning,
    _resolve_current_observed_learning_dates,
)
from ml_module.recommendation_calibration_training import RecommendationCalibrationSample
from ml_module.historical_feature_builder import CurrentObservedFeatureRow
from ml_module.recommendation_calibration_evidence import (
    _current_observed_raw_status_is_eligible,
    _verify_current_observed_entry_observation,
    load_current_observed_context_from_pinned_snapshot,
    verify_current_observed_cycle_reuse,
    verify_current_observed_input_capture,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def _create_entry_db(path: Path, *, stock_close: str = "123.4500", index_close: str = "23123.45") -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            'CREATE TABLE daily_prices ("證券代號" TEXT, "日期" TEXT, "收盤價" NUMERIC)'
        )
        connection.execute(
            'CREATE TABLE market_indices ("日期" TEXT, "收盤指數" NUMERIC, "收盤價" NUMERIC)'
        )
        connection.execute(
            'INSERT INTO daily_prices VALUES (?, ?, ?)',
            ("1477", "20261005", stock_close),
        )
        connection.execute(
            'INSERT INTO market_indices VALUES (?, ?, ?)',
            ("20261005", index_close, None),
        )


def _pins(
    database: Path,
    *,
    local_observed_at: str = "2026-10-05T07:00:00+00:00",
) -> dict[str, object]:
    return {
        "cycle_id": "raw-run-20261005",
        "raw_run_id": "raw-run-20261005",
        "cycle_terminal_path": "C:/repo/output/ml_research/cycle/terminal_receipt.json",
        "cycle_terminal_sha256": "sha256:" + "a" * 64,
        "snapshot_database_path": str(database.resolve()),
        "snapshot_database_sha256": _file_sha256(database),
        "snapshot_receipt_path": "C:/repo/output/ml_research/cycle/snapshot_receipt.json",
        "snapshot_receipt_sha256": "sha256:" + "b" * 64,
        "source_context_envelope_path": "C:/repo/output/ml_research/cycle/context.json",
        "source_context_envelope_sha256": "sha256:" + "c" * 64,
        "local_observed_at": local_observed_at,
    }


def _open_session_evidence(day: date, tmp_path: Path) -> dict[str, object]:
    from data_module.official_trading_calendar import OfficialTradingCalendar
    from data_module.official_trading_calendar_cache import (
        build_twse_calendar_cache,
        write_twse_calendar_cache,
    )

    cache_dir = tmp_path / "official" / "calendar"
    cache_path = cache_dir / f"twse_holiday_schedule_{day.year}_fixture.json"
    # Fixture evidence must predate every fixed intraday observation in this module.
    captured_at = min(
        datetime.now(timezone.utc) - timedelta(minutes=30),
        datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=1),
    )
    raw_response = json.dumps(
        [
            {
                "Date": f"{day.year - 1911:03d}0101",
                "Name": "New Year's Day",
                "Weekday": "Thursday",
                "Description": "Market closed",
            }
        ],
        separators=(",", ":"),
    ).encode("utf-8")
    cache = build_twse_calendar_cache(
        calendar_year=day.year,
        raw_response=raw_response,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
        response_url=(
            "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
            f"?queryYear={day.year - 1911}"
        ),
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    write_twse_calendar_cache(cache_path, cache, allowed_root=tmp_path)
    calendar = OfficialTradingCalendar(
        tmp_path / "unused-market.sqlite",
        calendar_cache_path=cache_dir,
    )
    evidence = calendar.evidence_for(day)
    assert evidence["mode"] == "hash_bound_official_calendar_cache"
    return evidence


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_current_entry_prices_pin_exact_same_day_decimal_rows_read_only(tmp_path: Path) -> None:
    database = tmp_path / "snapshot.sqlite"
    _create_entry_db(database)
    original_sha = _file_sha256(database)
    result = _read_current_observed_entry_prices(
        snapshot_database=database,
        expected_database_sha256=original_sha,
        decision_date=date(2026, 10, 5),
        cycle_source_date="2026-10-05",
        decision_session_evidence=_open_session_evidence(date(2026, 10, 5), tmp_path),
        symbols=("1477",),
        source_pins=_pins(database),
    )

    assert result["status"] == "captured"
    assert result["source_available_at"] is None
    assert result["historical_pit_eligible"] is False
    assert result["formal_training_allowed"] is False
    stock_pin = result["entry_price_pin_by_symbol"]["1477"]
    benchmark_pin = result["benchmark_entry_price_pin"]
    assert stock_pin["close_price_twd"] == "123.45"
    assert stock_pin["source_row_values"] == {
        "table": "daily_prices",
        "symbol": "1477",
        "source_date": "2026-10-05",
        "raw_close_value": "123.45",
    }
    assert stock_pin["source_row_sha256"].startswith("sha256:")
    assert benchmark_pin["symbol"] == "TAIEX"
    assert benchmark_pin["close_price_twd"] == "23123.45"
    assert stock_pin["local_observed_at"] == "2026-10-05T07:00:00+00:00"
    assert stock_pin["scheduled_market_close_at"] == "2026-10-05T13:30:00+08:00"
    assert stock_pin["entry_session_proof_sha256"] == result["entry_session_proof"]["proof_sha256"]
    assert _file_sha256(database) == original_sha
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0] == 1


def test_current_entry_observation_does_not_substitute_prior_session_for_sunday(
    tmp_path: Path,
) -> None:
    database = tmp_path / "snapshot.sqlite"
    _create_entry_db(database)
    result = _read_current_observed_entry_prices(
        snapshot_database=database,
        expected_database_sha256=_file_sha256(database),
        decision_date=date(2026, 10, 4),
        cycle_source_date="2026-10-02",
        decision_session_evidence=None,
        symbols=("1477",),
        source_pins=_pins(database),
    )

    assert result["status"] == "pending"
    assert result["reason"] == "same_date_entry_session_missing"
    assert result["entry_price_pin_by_symbol"] == {}
    assert result["benchmark_entry_price_pin"] is None


def test_current_entry_observation_rejects_ambiguous_duplicate_rows(tmp_path: Path) -> None:
    database = tmp_path / "snapshot.sqlite"
    _create_entry_db(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            'INSERT INTO daily_prices VALUES (?, ?, ?)',
            ("1477", "20261005", "124.00"),
        )

    result = _read_current_observed_entry_prices(
        snapshot_database=database,
        expected_database_sha256=_file_sha256(database),
        decision_date=date(2026, 10, 5),
        cycle_source_date="2026-10-05",
        decision_session_evidence=_open_session_evidence(date(2026, 10, 5), tmp_path),
        symbols=("1477",),
        source_pins=_pins(database),
    )

    assert result["status"] == "pending"
    assert result["reason"] == "same_date_stock_close_missing_or_ambiguous"
    assert result["missing_symbols"] == ["1477"]


def test_current_entry_pin_verifier_rechecks_row_hash_and_exact_close(tmp_path: Path) -> None:
    database = tmp_path / "snapshot.sqlite"
    _create_entry_db(database)
    pins = _pins(database)
    observation = _read_current_observed_entry_prices(
        snapshot_database=database,
        expected_database_sha256=_file_sha256(database),
        decision_date=date(2026, 10, 5),
        cycle_source_date="2026-10-05",
        decision_session_evidence=_open_session_evidence(date(2026, 10, 5), tmp_path),
        symbols=("1477",),
        source_pins=pins,
    )
    snapshot = {
        "decision_date": "2026-10-05",
        "cycle_source_date": "2026-10-05",
        "cycle_id": pins["cycle_id"],
        "raw_run_id": pins["raw_run_id"],
        "cycle_terminal_path": pins["cycle_terminal_path"],
        "cycle_terminal_sha256": pins["cycle_terminal_sha256"],
        "snapshot_database_path": str(database.resolve()),
        "snapshot_database_sha256": _file_sha256(database),
        "snapshot_receipt_path": pins["snapshot_receipt_path"],
        "snapshot_receipt_sha256": pins["snapshot_receipt_sha256"],
        "source_context_envelope_path": pins["source_context_envelope_path"],
        "source_context_envelope_sha256": pins["source_context_envelope_sha256"],
        "symbols": ["1477"],
    }

    _verify_current_observed_entry_observation(snapshot, observation)

    altered = {**observation, "entry_price_pin_by_symbol": dict(observation["entry_price_pin_by_symbol"])}
    altered_pin = dict(altered["entry_price_pin_by_symbol"]["1477"])
    altered_pin["close_price_twd"] = "124.00"
    altered["entry_price_pin_by_symbol"]["1477"] = altered_pin
    with pytest.raises(ValueError, match="entry price pin identity|exact source row"):
        _verify_current_observed_entry_observation(snapshot, altered)

    with sqlite3.connect(database) as connection:
        connection.execute(
            'UPDATE daily_prices SET "收盤價"=? WHERE "證券代號"=?',
            ("124.00", "1477"),
        )
    with pytest.raises(ValueError, match="source database hash mismatch"):
        _verify_current_observed_entry_observation(snapshot, observation)


def test_current_entry_clock_before_regular_close_stays_pending(tmp_path: Path) -> None:
    database = tmp_path / "snapshot.sqlite"
    _create_entry_db(database)
    pins = _pins(database, local_observed_at="2026-10-05T05:29:59+00:00")

    result = _read_current_observed_entry_prices(
        snapshot_database=database,
        expected_database_sha256=_file_sha256(database),
        decision_date=date(2026, 10, 5),
        cycle_source_date="2026-10-05",
        decision_session_evidence=_open_session_evidence(date(2026, 10, 5), tmp_path),
        symbols=("1477",),
        source_pins=pins,
    )

    assert result["status"] == "pending"
    assert result["reason"] == "entry_source_observation_before_scheduled_market_close"
    assert result["scheduled_market_close_at"] == "2026-10-05T13:30:00+08:00"
    assert result["entry_price_pin_by_symbol"] == {}
    assert result["benchmark_entry_price_pin"] is None


def test_current_entry_clock_after_close_verifier_recomputes_schedule(tmp_path: Path) -> None:
    database = tmp_path / "snapshot.sqlite"
    _create_entry_db(database)
    pins = _pins(database)
    observation = _read_current_observed_entry_prices(
        snapshot_database=database,
        expected_database_sha256=_file_sha256(database),
        decision_date=date(2026, 10, 5),
        cycle_source_date="2026-10-05",
        decision_session_evidence=_open_session_evidence(date(2026, 10, 5), tmp_path),
        symbols=("1477",),
        source_pins=pins,
    )
    snapshot = {
        "decision_date": "2026-10-05",
        "cycle_source_date": "2026-10-05",
        "cycle_id": pins["cycle_id"],
        "raw_run_id": pins["raw_run_id"],
        "cycle_terminal_path": pins["cycle_terminal_path"],
        "cycle_terminal_sha256": pins["cycle_terminal_sha256"],
        "snapshot_database_path": str(database.resolve()),
        "snapshot_database_sha256": _file_sha256(database),
        "snapshot_receipt_path": pins["snapshot_receipt_path"],
        "snapshot_receipt_sha256": pins["snapshot_receipt_sha256"],
        "source_context_envelope_path": pins["source_context_envelope_path"],
        "source_context_envelope_sha256": pins["source_context_envelope_sha256"],
        "symbols": ["1477"],
    }
    _verify_current_observed_entry_observation(snapshot, observation)

    altered = json.loads(json.dumps(observation))
    altered["entry_session_proof"]["scheduled_market_close_at"] = "2026-10-05T14:30:00+08:00"
    with pytest.raises(ValueError, match="official session calendar proof is invalid"):
        _verify_current_observed_entry_observation(snapshot, altered)


def test_current_entry_requires_verified_official_session_evidence(tmp_path: Path) -> None:
    database = tmp_path / "snapshot.sqlite"
    _create_entry_db(database)
    result = _read_current_observed_entry_prices(
        snapshot_database=database,
        expected_database_sha256=_file_sha256(database),
        decision_date=date(2026, 10, 5),
        cycle_source_date="2026-10-05",
        decision_session_evidence={
            **_open_session_evidence(date(2026, 10, 5), tmp_path),
            "is_trading_day": None,
        },
        symbols=("1477",),
        source_pins=_pins(database),
    )

    assert result["status"] == "pending"
    assert result["reason"] == "official_entry_session_calendar_unverified"


def test_current_entry_rejects_self_hashed_live_calendar_without_cache_custody(
    tmp_path: Path,
) -> None:
    database = tmp_path / "snapshot.sqlite"
    _create_entry_db(database)
    forged = {
        "mode": "live_official_calendar",
        "target_date": "2026-10-05",
        "is_trading_day": True,
        "reason_code": "twse_holiday_schedule_cache_open",
        "source_hash": "sha256:" + "a" * 64,
    }

    result = _read_current_observed_entry_prices(
        snapshot_database=database,
        expected_database_sha256=_file_sha256(database),
        decision_date=date(2026, 10, 5),
        cycle_source_date="2026-10-05",
        decision_session_evidence=forged,
        symbols=("1477",),
        source_pins=_pins(database),
    )

    assert result["status"] == "pending"
    assert result["reason"] == "official_entry_session_calendar_unverified"
    assert result["entry_price_pin_by_symbol"] == {}


def test_current_entry_verifier_rejects_mutated_calendar_cache(tmp_path: Path) -> None:
    database = tmp_path / "snapshot.sqlite"
    _create_entry_db(database)
    pins = _pins(database)
    session_evidence = _open_session_evidence(date(2026, 10, 5), tmp_path)
    observation = _read_current_observed_entry_prices(
        snapshot_database=database,
        expected_database_sha256=_file_sha256(database),
        decision_date=date(2026, 10, 5),
        cycle_source_date="2026-10-05",
        decision_session_evidence=session_evidence,
        symbols=("1477",),
        source_pins=pins,
    )
    assert observation["status"] == "captured"
    calendar_evidence = observation["entry_session_proof"]["calendar_evidence"]
    cache_path = Path(calendar_evidence["path"])
    cache_path.write_bytes(cache_path.read_bytes() + b" ")

    snapshot = {
        "decision_date": "2026-10-05",
        "cycle_source_date": "2026-10-05",
        "cycle_id": pins["cycle_id"],
        "raw_run_id": pins["raw_run_id"],
        "cycle_terminal_path": pins["cycle_terminal_path"],
        "cycle_terminal_sha256": pins["cycle_terminal_sha256"],
        "snapshot_database_path": str(database.resolve()),
        "snapshot_database_sha256": _file_sha256(database),
        "snapshot_receipt_path": pins["snapshot_receipt_path"],
        "snapshot_receipt_sha256": pins["snapshot_receipt_sha256"],
        "source_context_envelope_path": pins["source_context_envelope_path"],
        "source_context_envelope_sha256": pins["source_context_envelope_sha256"],
        "symbols": ["1477"],
    }
    with pytest.raises((ValueError, OSError), match="(?i)calendar|cache|hash|custody"):
        _verify_current_observed_entry_observation(snapshot, observation)


def test_identical_verified_same_day_capture_retry_deduplicates_but_keeps_stable_row() -> None:
    from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY

    feature_ids = CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids
    feature_values = tuple(range(len(feature_ids)))
    source_hashes = (
        ("daily_prices", "sha256:" + "1" * 64),
        ("technical_indicators", "sha256:" + "2" * 64),
        ("market_indices", "sha256:" + "3" * 64),
        ("industry_indices", "sha256:" + "4" * 64),
    )

    def feature_row(clock: datetime) -> CurrentObservedFeatureRow:
        return CurrentObservedFeatureRow(
            symbol="1477",
            decision_date="2026-10-05",
            feature_as_of_date="2026-10-02",
            local_current_observed_at=clock,
            cycle_id="raw-run-20261005",
            cycle_terminal_path="C:/repo/output/ml_research/cycle/terminal.json",
            cycle_terminal_sha256="sha256:" + "5" * 64,
            snapshot_database_path="C:/repo/output/ml_research/snapshot.sqlite",
            snapshot_database_sha256="sha256:" + "6" * 64,
            snapshot_receipt_path="C:/repo/output/ml_research/snapshot_receipt.json",
            snapshot_receipt_sha256="sha256:" + "7" * 64,
            source_context_envelope_path="C:/repo/output/ml_research/context.json",
            source_context_envelope_sha256="sha256:" + "8" * 64,
            source_row_sha256_by_table=source_hashes,
            feature_registry_id=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_id,
            feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
            feature_schema_hash="sha256:" + "9" * 64,
            feature_ids=feature_ids,
            values=tuple(zip(feature_ids, feature_values)),
            missing_feature_ids=(),
        )

    first_feature = feature_row(datetime(2026, 10, 5, 7, 0, tzinfo=timezone.utc))
    repeated_feature = feature_row(datetime(2026, 10, 5, 7, 1, tzinfo=timezone.utc))
    assert first_feature.row_sha256 != repeated_feature.row_sha256
    sample = RecommendationCalibrationSample(
        row_id="current-observed-natural:capture-one:row-one",
        symbol="1477",
        decision_date="2026-10-05",
        feature_as_of_date="2026-10-02",
        feature_available_date="2026-10-05",
        label_end_date="2026-11-02",
        label_available_date="2026-11-02",
        feature_values=feature_values,
        stock_return_bp=125,
        benchmark_return_bp=25,
        fixed_round_trip_cost_bp=50,
        observed_liquidity_cost_bp=None,
        rule_probability_bp=5000,
        upside_label=1,
        after_cost_profit_label=None,
        source_quality="current_observed_natural_research",
    )
    entry_pin = {
        "schema_version": "recommendation-current-observed-entry-price-pin.v1",
        "row_id": "current-observed:2026-10-05:raw-run-20261005:1477",
        "symbol": "1477",
        "source_date": "2026-10-05",
        "close_price_twd": "100.00",
        "raw_close_value": "100",
        "source_table": "daily_prices",
        "source_row_values": {
            "table": "daily_prices",
            "symbol": "1477",
            "source_date": "2026-10-05",
            "raw_close_value": "100",
        },
        "source_row_sha256": "sha256:" + "b" * 64,
        "cycle_id": "raw-run-20261005",
        "raw_run_id": "raw-run-20261005",
        "cycle_terminal_path": "C:/repo/output/ml_research/cycle/terminal.json",
        "cycle_terminal_sha256": "sha256:" + "5" * 64,
        "snapshot_database_path": "C:/repo/output/ml_research/snapshot.sqlite",
        "snapshot_database_sha256": "sha256:" + "6" * 64,
        "snapshot_receipt_path": "C:/repo/output/ml_research/snapshot_receipt.json",
        "snapshot_receipt_sha256": "sha256:" + "7" * 64,
        "source_context_envelope_path": "C:/repo/output/ml_research/context.json",
        "source_context_envelope_sha256": "sha256:" + "8" * 64,
        "local_observed_at": "2026-10-05T06:30:00+00:00",
        "source_available_at": None,
        "scheduled_market_close_at": "2026-10-05T13:30:00+08:00",
        "entry_session_proof_sha256": "sha256:" + "a" * 64,
        "current_restated": True,
        "research_only": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
    }

    def make_capture_row(row_id: str, feature: CurrentObservedFeatureRow) -> dict[str, object]:
        return {
            "row_id": row_id,
            "symbol": "1477",
            "decision_date": feature.decision_date,
            "feature_as_of_date": feature.feature_as_of_date,
            "feature_available_date": feature.decision_date,
            "feature_available_at": feature.local_current_observed_at.isoformat(),
            "feature_registry_id": feature.feature_registry_id,
            "feature_registry_hash": feature.feature_registry_hash,
            "feature_schema_hash": feature.feature_schema_hash,
            "feature_ids": list(feature.feature_ids),
            "feature_values": [value for _, value in feature.values],
            "source_row_sha256_by_table": [list(item) for item in feature.source_row_sha256_by_table],
            "feature_row_sha256": feature.row_sha256,
            "entry_price_pin": entry_pin,
        }

    later_clock_a = "2026-11-03T08:00:00+00:00"
    later_clock_b = "2026-11-03T08:01:00+00:00"
    capture_row = make_capture_row("capture-one:row-one", first_feature)
    outcome_row = {
        "capture_row_id": "capture-one:row-one",
        "capture_path": "C:/shadow/capture-one.json",
        "capture_sha256": "sha256:" + "c" * 64,
        "symbol": "1477",
        "capture_decision_date": "2026-10-05",
        "feature_as_of_date": "2026-10-02",
        "feature_available_date": "2026-10-05",
        "feature_available_at": first_feature.local_current_observed_at.isoformat(),
        "feature_row_sha256": first_feature.row_sha256,
        "feature_values": list(feature_values),
        "entry_price_proof": entry_pin,
        "entry_consistency_source_proof": {
            "source_row_sha256": "sha256:" + "b" * 64,
            "local_observed_at": later_clock_a,
            "proof_sha256": "sha256:" + "d" * 64,
        },
        "endpoint_price_proof": {
            "source_row_sha256": "sha256:" + "e" * 64,
            "raw_close_value": "101.25",
            "local_observed_at": later_clock_a,
            "proof_sha256": "sha256:" + "f" * 64,
        },
        "maturity_session_proof": {
            "session_dates": [f"2026-10-{day:02d}" for day in range(6, 26)],
            "calendar_raw_sha256": "sha256:" + "0" * 64,
            "local_observed_at": later_clock_a,
            "proof_sha256": "sha256:" + "1" * 64,
        },
        "label_observed_at": later_clock_a,
        "label_end_date": "2026-11-02",
        "label_available_date": "2026-11-03",
        "sell_price_twd": "101.25",
        "stock_return_bp": 125,
        "benchmark_return_bp": 25,
        "upside_label": 1,
        "cost_scenario_hash": sample.cost_scenario_hash,
    }
    repeat_capture_row = make_capture_row("capture-two:row-one", repeated_feature)
    repeat_outcome_row = {
        **outcome_row,
        "capture_row_id": "capture-two:row-one",
        "capture_path": "C:/shadow/capture-two.json",
        "capture_sha256": "sha256:" + "2" * 64,
        "feature_available_at": repeated_feature.local_current_observed_at.isoformat(),
        "feature_row_sha256": repeated_feature.row_sha256,
        "label_observed_at": later_clock_b,
        "entry_consistency_source_proof": {
            **outcome_row["entry_consistency_source_proof"],
            "local_observed_at": later_clock_b,
            "proof_sha256": "sha256:" + "3" * 64,
        },
        "endpoint_price_proof": {
            **outcome_row["endpoint_price_proof"],
            "local_observed_at": later_clock_b,
            "proof_sha256": "sha256:" + "4" * 64,
        },
        "maturity_session_proof": {
            **outcome_row["maturity_session_proof"],
            "local_observed_at": later_clock_b,
            "proof_sha256": "sha256:" + "5" * 64,
        },
    }

    first_hash = _current_observed_capture_semantic_hash(
        capture_row=capture_row,
        outcome_row=outcome_row,
    )
    repeated_hash = _current_observed_capture_semantic_hash(
        capture_row=repeat_capture_row,
        outcome_row=repeat_outcome_row,
    )
    assert first_hash == repeated_hash

    deduplicated = _deduplicate_current_observed_samples(
        [
            (sample, first_hash),
            (
                RecommendationCalibrationSample(
                    **{
                        **sample.__dict__,
                        "row_id": "current-observed-natural:capture-two:row-one",
                    }
                ),
                repeated_hash,
            ),
        ]
    )
    assert len(deduplicated) == 1
    assert deduplicated[0].row_id.startswith("current-observed-natural-semantic:")

    conflicting_capture_row = {
        **repeat_capture_row,
        "feature_values": [999, *list(feature_values[1:])],
        "source_row_sha256_by_table": [
            ["daily_prices", "sha256:" + "f" * 64],
            *[list(item) for item in source_hashes[1:]],
        ],
    }
    conflicting_hash = _current_observed_capture_semantic_hash(
        capture_row=conflicting_capture_row,
        outcome_row=repeat_outcome_row,
    )
    with pytest.raises(ValueError, match="conflicting immutable"):
        _deduplicate_current_observed_samples(
            [(sample, first_hash), (sample, conflicting_hash)]
        )


def test_rule_only_pointer_only_conflict_is_capture_lane_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.scheduled.run_daily_recommendation_learning as daily_learning

    monkeypatch.setattr(
        daily_learning,
        "_read_regular_file_no_follow",
        lambda path, _root, **_: Path(path).read_bytes(),
    )

    output_root = tmp_path / "learning-output"
    learning_root = output_root / "recommendation_learning"
    learning_root.mkdir(parents=True)
    pointer_path = learning_root / "recommendation-calibration-active-pointer.json"
    pointer_path.write_text(
        json.dumps(
            {
                "schema_version": "recommendation-calibration-active-pointer.v2",
                "status": "rule_only",
                "candidate_id": None,
                "candidate_root": None,
            }
        ),
        encoding="utf-8",
    )
    requested_args = daily_learning.build_parser().parse_args(
        ["--fixed-round-trip-cost-bp", "50"]
    )
    _, requested_scenario = daily_learning._cost_scenario_from_args(requested_args)
    conflict = _cost_scenario_root_conflict(output_root, requested_scenario)

    assert conflict is not None
    assert _is_rule_only_pointer_capture_lane_conflict(
        output_root, requested_scenario, conflict
    )

    other_args = daily_learning.build_parser().parse_args(
        ["--fixed-round-trip-cost-bp", "75"]
    )
    _, other_scenario = daily_learning._cost_scenario_from_args(other_args)
    pointer_path.write_text(
        json.dumps(
            {
                "schema_version": "recommendation-calibration-active-pointer.v2",
                "status": "rule_only",
                "candidate_id": None,
                "candidate_root": None,
                **daily_learning._scenario_cli_metadata(other_scenario),
            }
        ),
        encoding="utf-8",
    )
    mismatched_conflict = _cost_scenario_root_conflict(output_root, requested_scenario)

    assert mismatched_conflict is not None
    assert not _is_rule_only_pointer_capture_lane_conflict(
        output_root, requested_scenario, mismatched_conflict
    )


def test_daily_main_rule_only_pointer_allows_current_capture_but_blocks_formal_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from types import SimpleNamespace
    import scripts.scheduled.run_daily_recommendation_learning as daily_learning

    monkeypatch.setattr(
        daily_learning,
        "_read_regular_file_no_follow",
        lambda path, _root, **_: Path(path).read_bytes(),
    )

    output_root = tmp_path / "learning-output"
    data_root = tmp_path / "data"
    data_root.mkdir()
    scheduled_snapshot_root = tmp_path / "shadow-snapshots"
    canonical_raw_output_root = data_root / "output"
    scheduled_snapshot_root.mkdir()
    canonical_raw_output_root.mkdir(parents=True)
    learning_root = output_root / "recommendation_learning"
    learning_root.mkdir(parents=True)
    pointer_path = learning_root / "recommendation-calibration-active-pointer.json"
    pointer_path.write_text(
        json.dumps(
            {
                "schema_version": "recommendation-calibration-active-pointer.v2",
                "status": "rule_only",
                "candidate_id": None,
                "candidate_root": None,
            }
        ),
        encoding="utf-8",
    )
    pointer_before = pointer_path.read_bytes()
    decision_day = date(2026, 10, 5)
    observed_clock = datetime(2026, 10, 5, 16, 0, tzinfo=TAIPEI)
    monkeypatch.setattr(daily_learning, "_taipei_now", lambda: observed_clock)
    current_source_calls: list[dict[str, object]] = []

    def _capture_current_source_roots(**kwargs: object) -> dict[str, object]:
        current_source_calls.append(dict(kwargs))
        return {
            "status": "captured",
            "cycle_id": "cycle-current",
            "content_sha256": "sha256:" + "a" * 64,
            "observed_at": observed_clock.isoformat(),
        }

    monkeypatch.setattr(
        daily_learning,
        "_current_observed_feature_snapshot_for_learning",
        _capture_current_source_roots,
    )
    monkeypatch.setattr(
        daily_learning,
        "_audit_source_contract",
        lambda **_: {"source_contract_receipt": {"status": "pending"}},
    )
    capture_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        daily_learning,
        "_persist_current_observed_input_capture",
        lambda **kwargs: capture_calls.append(kwargs)
        or {"status": "pending", "reason": "fixture_no_capture_binding"},
    )
    monkeypatch.setattr(
        daily_learning,
        "_natural_maturity_calendar_paths",
        lambda **_: (tmp_path / "calendar.json", None),
    )
    monkeypatch.setattr(
        daily_learning,
        "NaturalMaturitySessionResolver",
        lambda **_: object(),
    )
    monkeypatch.setattr(
        daily_learning,
        "_current_observed_natural_research_fit",
        lambda **_: {
            "status": "pending",
            "reason": "fixture_waiting_for_mature_forward_rows",
            "historical_pit_eligible": False,
            "formal_training_allowed": False,
            "promotion_credit_created": False,
        },
    )
    calls: list[dict[str, object]] = []

    class _Runner:
        def run(self, **kwargs):
            calls.append(kwargs)
            assert kwargs["samples"] == ()
            assert kwargs["natural_evidence"] is None
            assert kwargs["data_dependency_status"] == "failed"
            assert kwargs["outcome_dependency_status"] == "failed"
            assert kwargs["emergency_rollback"] is False
            return SimpleNamespace(
                run_id=f"daily-recommendation-learning:{decision_day.isoformat()}",
                status="failed_dependency",
                reason="cost_scenario_root_conflict_fail_closed",
                receipt_path=str(learning_root / "runs" / "run_receipt.json"),
                latest_status_path=str(learning_root / "latest_status.json"),
                dataset_id=None,
                dataset_hash=None,
                candidate_id=None,
                candidate_root=None,
                training_lineage_manifest_hash=None,
                training_lineage_manifest_path=None,
                training_lineage_status="skipped",
                decision="retain_current",
                decision_reason="formal_dependency_failed",
                idempotent_replay=False,
            )

    monkeypatch.setattr(daily_learning, "_build_runner", lambda *_, **__: _Runner())
    args = [
        "--data-root",
        str(data_root),
        "--output-root",
        str(output_root),
        "--snapshot-output-root",
        str(scheduled_snapshot_root),
        "--current-observed-expected-raw-run-id",
        "raw-current-20261005",
        "--current-observed-expected-cycle-terminal",
        str(canonical_raw_output_root / "cycle" / "terminal.json"),
        "--current-observed-expected-cycle-terminal-sha256",
        "sha256:" + "b" * 64,
        "--source-db",
        str(tmp_path / "source.sqlite"),
        "--symbols",
        "1477",
    ]

    assert daily_learning.main(args) == 2
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["current_observed_capture_only_due_to_legacy_rule_pointer"] is True
    assert payload["formal_cost_lane_status"] == "blocked"
    assert payload["run"]["candidate_id"] is None
    assert len(capture_calls) == 1
    assert len(calls) == 1
    assert len(current_source_calls) == 1
    assert current_source_calls[0]["canonical_output_root"] == canonical_raw_output_root.resolve()
    assert current_source_calls[0]["expected_raw_run_id"] == "raw-current-20261005"
    assert current_source_calls[0]["expected_cycle_terminal_path"] == (
        canonical_raw_output_root / "cycle" / "terminal.json"
    )
    assert pointer_path.read_bytes() == pointer_before

    other_args = daily_learning.build_parser().parse_args(
        ["--fixed-round-trip-cost-bp", "75"]
    )
    _, other_scenario = daily_learning._cost_scenario_from_args(other_args)
    pointer_path.write_text(
        json.dumps(
            {
                "schema_version": "recommendation-calibration-active-pointer.v2",
                "status": "rule_only",
                "candidate_id": None,
                "candidate_root": None,
                **daily_learning._scenario_cli_metadata(other_scenario),
            }
        ),
        encoding="utf-8",
    )
    assert daily_learning.main(args) == 2
    blocked_payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert blocked_payload["decision_reason"] == "cost_scenario_root_conflict"
    assert len(capture_calls) == 1
    assert len(calls) == 1


def test_daily_runner_parser_accepts_current_observed_source_root_override() -> None:
    from scripts.scheduled.run_daily_recommendation_learning import build_parser

    custom_root = Path("E:/isolated/canonical-output")
    args = build_parser().parse_args(
        ["--current-observed-source-output-root", str(custom_root)]
    )
    assert args.current_observed_source_output_root == custom_root


def test_no_model_capture_verifier_rejects_probability_payload() -> None:
    with pytest.raises(ValueError, match="no-model"):
        verify_current_observed_input_capture(
            {
                "schema_version": "recommendation-current-observed-input-capture.v1",
                "status": "captured",
                "current_restated": True,
                "research_only": True,
                "historical_pit_eligible": False,
                "formal_training_allowed": False,
                "natural_outcome_only": True,
                "probability_bp": 5000,
            }
        )


def _write_pinned_context_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    keep_source_connection: bool = False,
) -> dict[str, object]:
    import json

    from data_module.ml_daily_price_revision_gate import VerifiedCurrentRestatedSourceContext
    from ml_module.current_restated_research_bridge import _source_context_plain_payload

    research_root = tmp_path / "repo" / "output" / "ml_research"
    cycle_root = research_root / "current_stock_cycles" / "2026-10-05" / "cycle-storage-key"
    cycle_root.mkdir(parents=True)
    monkeypatch.setattr(
        "ml_module.recommendation_calibration_evidence._CURRENT_OBSERVED_RESEARCH_ROOT",
        research_root,
    )
    source_db = tmp_path / "mutable" / "canonical.db"
    source_db.parent.mkdir()
    source_connection = sqlite3.connect(source_db)
    source_connection.execute("PRAGMA journal_mode=WAL")
    source_connection.execute("CREATE TABLE source_observation (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
    source_connection.execute("PRAGMA wal_autocheckpoint=0")
    source_connection.execute("INSERT INTO source_observation(value) VALUES (?)", ("captured",))
    source_connection.commit()
    source_wal = source_db.with_name(source_db.name + "-wal")
    snapshot_db = cycle_root / "snapshot" / "source.sqlite"
    snapshot_db.parent.mkdir()
    snapshot_connection = sqlite3.connect(snapshot_db)
    source_connection.backup(snapshot_connection)
    snapshot_connection.close()
    if keep_source_connection:
        assert source_wal.is_file()
    else:
        source_connection.close()
        if not source_wal.exists():
            source_wal.write_bytes(b"canonical WAL bytes at capture")
    receipt_path = cycle_root / "snapshot" / "snapshot_receipt.json"
    context_path = cycle_root / "context" / "source_context.json"
    context_path.parent.mkdir()
    completed_at = "2026-10-05T05:30:00+00:00"
    revision_verified_at = "2026-10-05T05:31:00+00:00"
    training_as_of = revision_verified_at
    snapshot_db_sha = _file_sha256(snapshot_db)
    source_db_sha = _file_sha256(source_db)
    placeholder_sha = "sha256:" + "a" * 64
    context = VerifiedCurrentRestatedSourceContext(
        source_database_path=str(source_db.resolve()),
        source_database_sha256=source_db_sha,
        source_wal_path=str(source_wal.resolve()),
        source_wal_sha256=_file_sha256(source_wal),
        snapshot_database_path=str(snapshot_db.resolve()),
        snapshot_database_sha256=snapshot_db_sha,
        snapshot_receipt_path=str(receipt_path.resolve()),
        snapshot_receipt_sha256=placeholder_sha,
        decision_at= datetime.fromisoformat(completed_at),
        training_as_of=datetime.fromisoformat(training_as_of),
        source_observed_at=datetime.fromisoformat(completed_at),
        source_generation=2,
        revision_namespace_files=(),
        revision_namespace_bundle_sha256=placeholder_sha,
        source_revision_evidence_schema_version="validated-source-evidence.v1",
        source_revision_evidence_scope_id="ml_daily_price_revision_gate.v1",
        source_revision_evidence_cutoff_date="2026-10-05",
        source_revision_evidence_sha256=placeholder_sha,
        source_revision_evidence_namespaces=(),
        source_revision_evidence_files=(),
        revision_dependencies_verified_at=datetime.fromisoformat(revision_verified_at),
        revision_dependency_files=(),
        revision_dependency_bundle_sha256=placeholder_sha,
        current_restated=True,
        historical_pit_eligible=False,
        source_wal_present=True,
    )
    # The snapshot receipt hash is part of the context, so create a deterministic
    # receipt first, then reconstruct the context with its final actual hash.
    receipt = {
        "schema_version": "integration-consistent-sqlite-snapshot.v1",
        "status": "consistent_snapshot_created",
        "consistency": "sqlite_backup_from_single_query_only_read_transaction",
        "snapshot_quick_check": "ok",
        "source_and_revision_bytes_unchanged": True,
        "completed_at": completed_at,
        "snapshot": {
            "path": str(snapshot_db.resolve()),
            "sha256": snapshot_db_sha[7:],
            "bytes": snapshot_db.stat().st_size,
            "mtime_ns": snapshot_db.stat().st_mtime_ns,
        },
        "source_database_path": str(source_db.resolve()),
        "source_observation": {
            "database": {
                "path": str(source_db.resolve()),
                "sha256": source_db_sha[7:],
            }
        },
    }
    receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2), encoding="utf-8")
    from dataclasses import replace

    context = replace(context, snapshot_receipt_sha256=_file_sha256(receipt_path))
    # Rehydrating from a serialized payload is intentionally avoided in runtime;
    # the fixture uses the typed dataclass then its canonical serializer.
    envelope = {
        "schema_version": "ml-current-restated-source-context-envelope.v1",
        "source_context": _source_context_plain_payload(context),
    }
    context_bytes = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    context_path.write_bytes(context_bytes)
    context_sha = "sha256:" + hashlib.sha256(context_bytes).hexdigest()
    terminal_path = cycle_root / "terminal_receipt.json"
    terminal_pins = {
        "snapshot_database_path": str(snapshot_db.resolve()),
        "snapshot_database_sha256": snapshot_db_sha,
        "snapshot_receipt_path": str(receipt_path.resolve()),
        "snapshot_receipt_sha256": _file_sha256(receipt_path),
        "source_context_envelope_path": str(context_path.resolve()),
        "source_context_envelope_sha256": context_sha,
        "snapshot_completed_at": completed_at,
        "revision_dependencies_verified_at": revision_verified_at,
        "current_restated_training_as_of": training_as_of,
    }
    terminal = {
        "schema_version": "current-stock-research-cycle-terminal.v1",
        "status": "completed",
        "cycle_id": "raw-run-20261005",
        "raw_run_id": "raw-run-20261005",
        "source_date": "2026-10-05",
        "same_run_pins": terminal_pins,
    }
    terminal_bytes = json.dumps(terminal, sort_keys=True, separators=(",", ":")).encode("utf-8")
    terminal_path.write_bytes(terminal_bytes)
    terminal_sha = "sha256:" + hashlib.sha256(terminal_bytes).hexdigest()
    return {
        "cycle_id": "raw-run-20261005",
        "raw_run_id": "raw-run-20261005",
        "cycle_source_date": "2026-10-05",
        "cycle_terminal_path": str(terminal_path.resolve()),
        "cycle_terminal_sha256": terminal_sha,
        "snapshot_database_path": str(snapshot_db.resolve()),
        "snapshot_database_sha256": snapshot_db_sha,
        "snapshot_receipt_path": str(receipt_path.resolve()),
        "snapshot_receipt_sha256": _file_sha256(receipt_path),
        "source_context_envelope_path": str(context_path.resolve()),
        "source_context_envelope_sha256": context_sha,
        "observed_at": "2026-10-05T05:32:00+00:00",
        "mutable_source_database": source_db,
        "mutable_source_wal": source_wal,
        "mutable_source_connection": source_connection if keep_source_connection else None,
        "mutable_source_database_sha256": source_db_sha,
        "mutable_source_wal_sha256": _file_sha256(source_wal),
        "frozen_snapshot_database": snapshot_db,
        "snapshot_receipt": receipt_path,
        "context_envelope": context_path,
        "cycle_terminal": terminal_path,
    }


def test_pinned_context_survives_mutable_source_changes_and_rejects_frozen_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _write_pinned_context_fixture(tmp_path, monkeypatch, keep_source_connection=True)
    mutable_source = fixture["mutable_source_database"]
    mutable_wal = fixture["mutable_source_wal"]
    mutable_connection = fixture["mutable_source_connection"]
    assert isinstance(mutable_source, Path)
    assert isinstance(mutable_wal, Path)
    assert isinstance(mutable_connection, sqlite3.Connection)
    mutable_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    mutable_connection.execute(
        "INSERT INTO source_observation(value) VALUES (?)",
        ("normal later source DB update",),
    )
    mutable_connection.commit()
    assert _file_sha256(mutable_source) != fixture["mutable_source_database_sha256"]
    assert _file_sha256(mutable_wal) != fixture["mutable_source_wal_sha256"]
    context = load_current_observed_context_from_pinned_snapshot(fixture)
    mutable_connection.close()
    assert context.current_restated is True
    assert context.historical_pit_eligible is False
    assert context.snapshot_database_path == fixture["snapshot_database_path"]

    for key, replacement, message in (
        ("frozen_snapshot_database", b"tampered snapshot", "snapshot_database_path"),
        ("snapshot_receipt", b"{}", "snapshot_receipt_path"),
        ("context_envelope", b"{}", "source_context_envelope_path"),
        ("cycle_terminal", b"{}", "cycle_terminal_path"),
    ):
        fresh = _write_pinned_context_fixture(tmp_path / key, monkeypatch)
        path = fresh[key]
        assert isinstance(path, Path)
        path.write_bytes(replacement)
        with pytest.raises(ValueError, match=message):
            load_current_observed_context_from_pinned_snapshot(fresh)


def test_current_observed_raw_status_allows_only_exact_formal_revision_block() -> None:
    blocked = {
        "schema_version": "ml-raw-pit-refresh-status.v1",
        "status": "blocked_source_revision",
        "error_type": "DailyPriceSourceRevisionError",
        "source_revision_gate": {
            "blocker_kind": "temporal_source_revision",
            "status": "blocked",
            "guard": "data_module.ml_daily_price_revision_gate.check_daily_price_source_revision",
            "receipt_reference_is_immutable_evidence": False,
        },
    }
    assert _current_observed_raw_status_is_eligible(blocked)
    assert not _current_observed_raw_status_is_eligible({**blocked, "status": "failed"})
    assert not _current_observed_raw_status_is_eligible(
        {**blocked, "source_revision_gate": {**blocked["source_revision_gate"], "status": "completed"}}
    )


def test_formal_revision_block_does_not_hide_exact_completed_current_cycle(tmp_path: Path) -> None:
    output_root = (tmp_path / "canonical-output").resolve()
    payload = {
        "schema_version": "ml-raw-pit-refresh-status.v1",
        "status": "blocked_source_revision",
        "error_type": "DailyPriceSourceRevisionError",
        "source_revision_gate": {
            "blocker_kind": "temporal_source_revision",
            "status": "blocked",
            "guard": "data_module.ml_daily_price_revision_gate.check_daily_price_source_revision",
            "receipt_reference_is_immutable_evidence": False,
        },
        "output_root": str(output_root),
        "run_id": "raw-run-20261002-a",
        "source_date": None,
        "latest_core_date": "2026-10-02",
        "current_stock_research_cycle": {
            "status": "completed",
            "raw_run_id": "raw-run-20261002-a",
            "source_date": "2026-10-02",
            "terminal_receipt_path": "C:/repo/output/ml_research/cycle/terminal_receipt.json",
            "terminal_receipt_sha256": "sha256:" + "a" * 64,
        },
    }

    assert _current_observed_raw_cycle_discovery_problem(
        payload,
        canonical_output_root=output_root,
        expected_source_date="2026-10-02",
    ) is None
    assert _current_observed_raw_cycle_discovery_problem(
        {**payload, "current_stock_research_cycle": {**payload["current_stock_research_cycle"], "status": "failed"}},
        canonical_output_root=output_root,
        expected_source_date="2026-10-02",
    ) == "current_stock_cycle_is_not_the_expected_successful_or_verified_reuse_raw_run"


def test_current_raw_discovery_can_require_exact_waited_run_and_terminal_pins(
    tmp_path: Path,
) -> None:
    output_root = (tmp_path / "canonical-output").resolve()
    terminal_path = tmp_path / "repo" / "output" / "ml_research" / "cycle" / "terminal.json"
    terminal_path.parent.mkdir(parents=True)
    terminal_path.write_text("{}", encoding="utf-8")
    terminal_sha = _file_sha256(terminal_path)
    payload = {
        "schema_version": "ml-raw-pit-refresh-status.v1",
        "status": "blocked_source_revision",
        "error_type": "DailyPriceSourceRevisionError",
        "source_revision_gate": {
            "blocker_kind": "temporal_source_revision",
            "status": "blocked",
            "guard": "data_module.ml_daily_price_revision_gate.check_daily_price_source_revision",
            "receipt_reference_is_immutable_evidence": False,
        },
        "output_root": str(output_root),
        "run_id": "raw-current-20261002",
        "latest_core_date": "2026-10-02",
        "current_stock_research_cycle": {
            "status": "completed",
            "raw_run_id": "raw-current-20261002",
            "source_date": "2026-10-02",
            "terminal_receipt_path": str(terminal_path.resolve()),
            "terminal_receipt_sha256": terminal_sha,
        },
    }
    expected = {
        "canonical_output_root": output_root,
        "expected_source_date": "2026-10-02",
        "expected_raw_run_id": "raw-current-20261002",
        "expected_cycle_terminal_path": terminal_path,
        "expected_cycle_terminal_sha256": terminal_sha,
    }

    assert _current_observed_raw_cycle_discovery_problem(payload, **expected) is None
    assert _current_observed_raw_cycle_discovery_problem(
        payload,
        **{**expected, "expected_raw_run_id": "stale-raw-run"},
    ) == "canonical_raw_status_run_differs_from_expected_run"
    assert _current_observed_raw_cycle_discovery_problem(
        payload,
        **{**expected, "expected_cycle_terminal_sha256": "sha256:" + "a" * 64},
    ) == "canonical_raw_status_terminal_sha_differs_from_expected_terminal"
    assert _current_observed_raw_cycle_discovery_problem(
        payload,
        **{**expected, "expected_cycle_terminal_path": tmp_path / "wrong-terminal.json"},
    ) == "expected_current_stock_cycle_terminal_path_is_unreadable"
    assert _current_observed_raw_cycle_discovery_problem(
        payload,
        expected_source_date="2026-10-02",
        canonical_output_root=output_root,
        expected_raw_run_id="raw-current-20261002",
    ) == "expected_current_stock_cycle_identity_is_incomplete"


def test_current_feature_snapshot_requires_exact_waited_g6_identity(tmp_path: Path) -> None:
    from types import SimpleNamespace

    result = _current_observed_feature_snapshot_for_learning(
        canonical_output_root=tmp_path / "canonical-output",
        config=SimpleNamespace(db_file=tmp_path / "data" / "stock.sqlite"),
        decision_date=date(2026, 10, 5),
        history_start_date="2020-01-01",
        symbols=("1477",),
        observed_at=datetime(2026, 10, 5, 16, 0, tzinfo=TAIPEI),
    )

    assert result["status"] == "pending"
    assert result["reason"] == "current_stock_cycle_exact_waited_identity_missing"


@pytest.mark.parametrize(
    ("decision_date", "observed_at", "expected_source_date", "expected_feature_date"),
    [
        (
            date(2026, 10, 5),
            datetime(2026, 10, 5, 11, 29, tzinfo=timezone.utc),
            "2026-10-02",
            "2026-10-02",
        ),
        (
            date(2026, 10, 5),
            datetime(2026, 10, 5, 11, 31, tzinfo=timezone.utc),
            "2026-10-05",
            "2026-10-02",
        ),
        (
            date(2026, 10, 4),
            datetime(2026, 10, 4, 12, 45, tzinfo=timezone.utc),
            "2026-10-02",
            "2026-10-02",
        ),
        # The Pacific cutoff is PST after the November DST transition.
        (
            date(2026, 11, 2),
            datetime(2026, 11, 2, 12, 29, tzinfo=timezone.utc),
            "2026-10-30",
            "2026-10-30",
        ),
        (
            date(2026, 11, 2),
            datetime(2026, 11, 2, 12, 31, tzinfo=timezone.utc),
            "2026-11-02",
            "2026-10-30",
        ),
    ],
)
def test_g6_source_date_cutoff_is_separate_from_prior_feature_session(
    tmp_path: Path,
    decision_date: date,
    observed_at: datetime,
    expected_source_date: str,
    expected_feature_date: str,
) -> None:
    cache_reference_date = (
        decision_date
        if decision_date.weekday() < 5
        else decision_date + timedelta(days=1)
    )
    _open_session_evidence(cache_reference_date, tmp_path)

    source_date, feature_date, decision_evidence = _resolve_current_observed_learning_dates(
        decision_date=decision_date,
        observed_at=observed_at,
        source_db=tmp_path / "calendar-only.sqlite",
        calendar_cache_path=tmp_path / "official" / "calendar",
        temporary_closure_path=None,
    )

    assert source_date == expected_source_date
    assert feature_date == expected_feature_date
    assert date.fromisoformat(feature_date) < decision_date
    if expected_source_date == decision_date.isoformat():
        assert decision_evidence is not None
    else:
        assert decision_evidence is None


def test_g6_source_date_respects_official_closure_after_cutoff(tmp_path: Path) -> None:
    from data_module.official_trading_calendar_cache import (
        build_twse_calendar_cache,
        write_twse_calendar_cache,
    )

    cache_dir = tmp_path / "official" / "calendar"
    cache_dir.mkdir(parents=True)
    captured_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    raw_response = json.dumps(
        [
            {
                "Date": "1151005",
                "Name": "Official Market Closure",
                "Weekday": "Monday",
                "Description": "Market closed",
            }
        ],
        separators=(",", ":"),
    ).encode("utf-8")
    cache = build_twse_calendar_cache(
        calendar_year=2026,
        raw_response=raw_response,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
        response_url="https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule?queryYear=115",
    )
    write_twse_calendar_cache(
        cache_dir / "twse_holiday_schedule_2026_fixture.json",
        cache,
        allowed_root=tmp_path,
    )

    source_date, feature_date, decision_evidence = _resolve_current_observed_learning_dates(
        decision_date=date(2026, 10, 5),
        observed_at=datetime(2026, 10, 5, 11, 31, tzinfo=timezone.utc),
        source_db=tmp_path / "calendar-only.sqlite",
        calendar_cache_path=cache_dir,
        temporary_closure_path=None,
    )

    assert source_date == "2026-10-02"
    assert feature_date == "2026-10-02"
    assert decision_evidence is None


def test_g6_source_date_fails_closed_when_official_calendar_is_missing(tmp_path: Path) -> None:
    missing_calendar = tmp_path / "missing-calendar"
    missing_calendar.mkdir()

    with pytest.raises(RuntimeError, match="official trading calendar unresolved"):
        _resolve_current_observed_learning_dates(
            decision_date=date(2026, 10, 5),
            observed_at=datetime(2026, 10, 5, 11, 31, tzinfo=timezone.utc),
            source_db=tmp_path / "calendar-only.sqlite",
            calendar_cache_path=missing_calendar,
            temporary_closure_path=None,
        )


def test_current_feature_snapshot_stays_pending_when_calendar_cannot_resolve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    import scripts.scheduled.run_daily_recommendation_learning as daily_learning

    now = datetime.now(TAIPEI) - timedelta(seconds=1)
    monkeypatch.setattr(
        daily_learning,
        "_natural_maturity_calendar_paths",
        lambda **_: (tmp_path / "missing-calendar", None),
    )

    result = _current_observed_feature_snapshot_for_learning(
        canonical_output_root=tmp_path / "canonical-output",
        config=SimpleNamespace(db_file=tmp_path / "source.sqlite"),
        decision_date=now.date(),
        history_start_date="2020-01-01",
        symbols=("1477",),
        observed_at=now,
        expected_raw_run_id="raw-current-run",
        expected_cycle_terminal_path=tmp_path / "terminal.json",
        expected_cycle_terminal_sha256="sha256:" + "a" * 64,
    )

    assert result["status"] == "pending"
    assert result["reason"] == "official_calendar_could_not_resolve_current_and_prior_sessions"


def _current_outcome_fixture() -> tuple[dict[str, object], dict[str, object]]:
    from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
    from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario

    scenario = build_legacy_cost_scenario(80)
    row_id = "capture-row-1477"
    feature_values = [0 for _ in CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids]
    capture_row = {
        "row_id": row_id,
        "symbol": "1477",
        "decision_date": "2026-09-01",
        "feature_as_of_date": "2026-08-31",
        "feature_available_date": "2026-09-01",
        "feature_row_sha256": "sha256:" + "a" * 64,
        "feature_values": feature_values,
    }
    capture: dict[str, object] = {
        "capture_id": "capture-20260901-a",
        "capture_sha256": "sha256:" + "b" * 64,
        "decision_date": "2026-09-01",
        "rows": [capture_row],
        "fixed_round_trip_cost_bp": 80,
        "cost_scenario": scenario.metadata(),
        "cost_scenario_id": scenario.scenario_id,
        "cost_scenario_version": scenario.scenario_version,
        "cost_scenario_hash": scenario.scenario_hash,
        "cost_basis": scenario.cost_basis,
        "cost_status": "verified",
    }
    outcome_row = {
        "capture_row_id": row_id,
        "symbol": "1477",
        "capture_decision_date": "2026-09-01",
        "feature_as_of_date": "2026-08-31",
        "feature_available_date": "2026-09-01",
        "feature_values": feature_values,
        "feature_row_sha256": "sha256:" + "a" * 64,
        "label_end_date": "2026-09-29",
        "label_available_date": "2026-09-30",
        "label_observed_at": "2026-09-30T14:00:00+08:00",
        "source_available_at": None,
        "stock_return_bp": 250,
        "benchmark_return_bp": 100,
        "upside_label": 1,
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "research_only": True,
        "cost_scenario_hash": scenario.scenario_hash,
        "cost_scenario_id": scenario.scenario_id,
        "cost_scenario_version": scenario.scenario_version,
        "cost_basis": scenario.cost_basis,
    }
    outcome: dict[str, object] = {
        "verification_status": "verified",
        "status": "matured",
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "research_only": True,
        "natural_outcome_only": True,
        "promotion_credit_created": False,
        "historical_replay_is_natural_evidence": False,
        "capture_id": capture["capture_id"],
        "capture_sha256": capture["capture_sha256"],
        "matured_sample_count": 1,
        "outcomes": [outcome_row],
    }
    return capture, outcome


def test_verified_current_observed_outcome_becomes_only_null_baseline_research_sample() -> None:
    from ml_module.recommendation_probability_transform import (
        NULL_BENCHMARK_BASELINE_ID,
        NULL_BENCHMARK_PROBABILITY_BP,
    )

    capture, outcome = _current_outcome_fixture()
    samples = _current_observed_outcome_samples(
        capture=capture,
        outcome=outcome,
        training_as_of=date(2026, 10, 3),
        feature_count=len(capture["rows"][0]["feature_values"]),
    )

    assert len(samples) == 1
    assert samples[0].rule_baseline_id == NULL_BENCHMARK_BASELINE_ID
    assert samples[0].rule_probability_bp == NULL_BENCHMARK_PROBABILITY_BP
    assert samples[0].source_quality == "current_observed_natural_research"
    assert samples[0].decision_date == "2026-09-01"
    assert samples[0].after_cost_profit_label is None
    assert samples[0].rule_after_cost_probability_bp is None
    assert samples[0].rule_after_cost_baseline_id is None


def test_estimated_cost_receipt_is_retained_without_creating_after_cost_prediction() -> None:
    from ml_module.recommendation_cost_scenario import build_banktaiwan_cost_scenario

    capture, outcome = _current_outcome_fixture()
    scenario = build_banktaiwan_cost_scenario(
        policy_estimate_date="2026-09-01",
        research_order_amount_twd="10000.00",
    )
    capture["fixed_round_trip_cost_bp"] = None
    capture["cost_scenario"] = scenario.metadata()
    capture["cost_scenario_id"] = scenario.scenario_id
    capture["cost_scenario_version"] = scenario.scenario_version
    capture["cost_scenario_hash"] = scenario.scenario_hash
    capture["cost_basis"] = scenario.cost_basis
    outcome_row = outcome["outcomes"][0]
    assert isinstance(outcome_row, dict)
    outcome_row.update(
        {
            "cost_scenario_hash": scenario.scenario_hash,
            "cost_scenario_id": scenario.scenario_id,
            "cost_scenario_version": scenario.scenario_version,
            "cost_basis": scenario.cost_basis,
            "cost_estimate_status": "estimated",
            "estimated_round_trip_cost_bp": 6,
            "estimated_buy_cost_twd": "2.00",
            "estimated_sell_cost_twd": "4.00",
            "estimated_round_trip_cost_twd": "6.00",
            "gross_buy_amount_twd": "10000.00",
            "gross_sell_amount_twd": "10100.00",
            "net_profit_twd": "94.00",
            "after_cost_profit_label": 1,
        }
    )
    outcome["matured_sample_count"] = 1

    samples = _current_observed_outcome_samples(
        capture=capture,
        outcome=outcome,
        training_as_of=date(2026, 10, 3),
        feature_count=len(capture["rows"][0]["feature_values"]),
    )

    sample = samples[0]
    assert sample.cost_basis == "estimated_research_only"
    assert sample.estimated_round_trip_cost_bp == 6
    assert sample.estimated_buy_cost_twd == "2.00"
    assert sample.estimated_sell_cost_twd == "4.00"
    assert sample.estimated_round_trip_cost_twd == "6.00"
    assert sample.gross_buy_amount_twd == "10000.00"
    assert sample.gross_sell_amount_twd == "10100.00"
    assert sample.net_profit_twd == "94.00"
    assert sample.after_cost_profit_label is None
    assert sample.rule_after_cost_probability_bp is None
    assert sample.rule_after_cost_baseline_id is None


@pytest.mark.parametrize(
    "flag,invalid_value",
    (("historical_pit_eligible", True), ("formal_training_allowed", 0), ("promotion_credit_created", 1)),
)
def test_current_observed_outcome_sample_rejects_qualification_or_promotion_flags(
    flag: str,
    invalid_value: object,
) -> None:
    capture, outcome = _current_outcome_fixture()
    outcome[flag] = invalid_value

    with pytest.raises(ValueError, match="identity or qualification"):
        _current_observed_outcome_samples(
            capture=capture,
            outcome=outcome,
            training_as_of=date(2026, 10, 3),
            feature_count=len(capture["rows"][0]["feature_values"]),
        )


def _write_json_pin(path: Path, payload: dict[str, object]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(encoded)
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _reuse_cycle_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    registry_run_id: str = "registry-20261005-a",
) -> tuple[Path, str, Path]:
    import ml_module.recommendation_calibration_evidence as evidence_module

    research_root = tmp_path / "output" / "ml_research"
    monkeypatch.setattr(evidence_module, "_CURRENT_OBSERVED_RESEARCH_ROOT", research_root)
    cycles_root = research_root / "current_stock_cycles"
    source_date = "2026-10-05"
    symbol = "1477"
    fingerprint = "a" * 64
    common_pins: dict[str, object] = {
        "reuse_key_sha256": "sha256:" + "e" * 64,
        "current_source_observation": {
            "snapshot_database_sha256": "sha256:" + "b" * 64,
            "source_context_sha256": "sha256:" + "c" * 64,
            "source_rows_sha256_by_table": {"daily_prices": "sha256:" + "d" * 64},
            "database": {
                "path": str((research_root / "source.sqlite").resolve()),
                "bytes": 4096,
                "mtime_ns": 100,
                "sha256": "1" * 64,
            },
            "wal": {
                "status": "present",
                "present": True,
                "path": str((research_root / "source.sqlite-wal").resolve()),
                "bytes": 0,
                "mtime_ns": 101,
                "sha256": "2" * 64,
            },
            "revision_namespace_files": [
                {
                    "namespace": "fixture_revision",
                    "path": str((research_root / "revision.json").resolve()),
                    "bytes": 12,
                    "mtime_ns": 102,
                    "sha256": "3" * 64,
                }
            ],
            "shared_memory_before": {
                "path": str((research_root / "source.sqlite-shm").resolve()),
                "bytes": 32768,
                "mtime_ns": 103,
                "sha256": "4" * 64,
            },
            "shared_memory_after": {
                "path": str((research_root / "source.sqlite-shm").resolve()),
                "bytes": 32768,
                "mtime_ns": 104,
                "sha256": "4" * 64,
            },
            "source_generation": 2,
            "journal_mode": "wal",
            "journal_mode_before": "wal",
            "journal_mode_after": "wal",
            "journal_mode_reader": "sqlite_pragma",
        },
        "current_price_row_fingerprint_sha256_by_symbol": {symbol: fingerprint},
        "official_raw_input_identity": {"source_date": source_date, "sha256": "f" * 64},
        "b_semantic_identity": {"source_date": source_date, "rows_sha256": "1" * 64},
    }
    scope_payloads: list[dict[str, object]] = []
    for run_id in ("raw-original", "raw-reuse"):
        scope_payloads.append(
            {
                "schema_version": "current-stock-research-cycle-scope.v1",
                "raw_run_id": run_id,
                "source_date": source_date,
                "current_symbols": [symbol],
                "watchlist_symbols": [symbol],
                "holding_symbols": [],
                "watchlist_input_pins": {"sha256": "2" * 64},
                "position_input_pins": {"sha256": "3" * 64},
                "watchlist_storage": "canonical",
            }
        )
    scope_paths = [cycles_root / "original" / "scope.json", cycles_root / "reuse" / "scope.json"]
    scope_hashes = [_write_json_pin(path, payload) for path, payload in zip(scope_paths, scope_payloads)]

    registry_path = (
        research_root
        / "current_stock_research_registry"
        / "runs"
        / registry_run_id
        / "record.json"
    )
    registry_payload: dict[str, object] = {
        "schema_version": "current-restated-stock-research-registry.v1",
        "run_id": registry_run_id,
        "status": "verified_research_sidecar",
        "scope_mode": "current_stock_research",
        "cycle_id": "raw-original",
        "event_date": source_date,
        "symbols": [symbol],
        "current_price_row_fingerprint_sha256_by_symbol": {symbol: fingerprint},
        "historical_pit_eligible": False,
        "formal_qualified": False,
        "production_action_allowed": False,
    }
    registry_hash = _write_json_pin(registry_path, registry_payload)
    registry_hash_hex = registry_hash.removeprefix("sha256:")
    original_terminal_path = cycles_root / "original" / "terminal_receipt.json"
    original_registry = {
        "run_id": registry_run_id,
        "record_path": str(registry_path.resolve()),
        "record_sha256": registry_hash_hex,
        "index_path": str((research_root / "current_stock_research_registry" / "index.jsonl").resolve()),
        "index_sha256_at_completion": "4" * 64,
    }
    original_terminal: dict[str, object] = {
        "schema_version": "current-stock-research-cycle-terminal.v1",
        "status": "completed",
        "raw_run_id": "raw-original",
        "cycle_id": "raw-original",
        "source_date": source_date,
        "current_symbols": [symbol],
        "historical_pit_eligible": False,
        "formal_training_eligible": False,
        "production_action_allowed": False,
        "same_run_pins": {
            **common_pins,
            "scope_manifest_path": str(scope_paths[0].resolve()),
            "scope_manifest_sha256": scope_hashes[0],
        },
        "registry": original_registry,
    }
    original_terminal_sha = _write_json_pin(original_terminal_path, original_terminal)

    reuse_terminal_path = cycles_root / "reuse" / "terminal_receipt.json"
    reuse_terminal: dict[str, object] = {
        "schema_version": "current-stock-research-cycle-terminal.v1",
        "status": "skipped_same_inputs",
        "raw_run_id": "raw-reuse",
        "cycle_id": "raw-reuse",
        "source_date": source_date,
        "current_symbols": [symbol],
        "historical_pit_eligible": False,
        "formal_training_eligible": False,
        "production_action_allowed": False,
        "same_run_pins": {
            **common_pins,
            "scope_manifest_path": str(scope_paths[1].resolve()),
            "scope_manifest_sha256": scope_hashes[1],
        },
        "reused_from": {
            "raw_run_id": "raw-original",
            "cycle_id": "raw-original",
            "terminal_receipt_path": str(original_terminal_path.resolve()),
            "terminal_receipt_sha256": original_terminal_sha,
            "registry_record_path": original_registry["record_path"],
            "registry_record_sha256": registry_hash,
            "registry_index_path": original_registry["index_path"],
            "registry_index_sha256_at_reuse": "sha256:" + "5" * 64,
            "last_success_at": "2026-10-05T06:01:00+08:00",
        },
    }
    _write_json_pin(reuse_terminal_path, reuse_terminal)
    return reuse_terminal_path, _file_sha256(reuse_terminal_path), registry_path


def test_current_observed_cycle_reuse_verifies_new_to_original_terminal_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest, _ = _reuse_cycle_fixture(tmp_path, monkeypatch)

    verified = verify_current_observed_cycle_reuse(
        reuse_terminal_path=path,
        reuse_terminal_sha256=digest,
        expected_raw_run_id="raw-reuse",
        expected_source_date="2026-10-05",
    )

    assert verified["discovery_raw_run_id"] == "raw-reuse"
    assert verified["original_raw_run_id"] == "raw-original"
    assert verified["source_date"] == "2026-10-05"


def test_current_observed_cycle_reuse_allows_only_shared_memory_mtime_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _digest, _ = _reuse_cycle_fixture(tmp_path, monkeypatch)
    reuse_terminal = json.loads(path.read_text(encoding="utf-8"))
    pins = reuse_terminal["same_run_pins"]
    observation = pins["current_source_observation"]
    observation["shared_memory_before"]["mtime_ns"] += 10_000
    observation["shared_memory_after"]["mtime_ns"] += 20_000
    digest = _write_json_pin(path, reuse_terminal)

    verified = verify_current_observed_cycle_reuse(
        reuse_terminal_path=path,
        reuse_terminal_sha256=digest,
        expected_raw_run_id="raw-reuse",
        expected_source_date="2026-10-05",
    )

    assert verified["discovery_raw_run_id"] == "raw-reuse"
    assert verified["original_raw_run_id"] == "raw-original"


@pytest.mark.parametrize(
    ("pin_path", "replacement"),
    [
        (("database", "mtime_ns"), 999),
        (("database", "sha256"), "9" * 64),
        (("wal", "mtime_ns"), 999),
        (("wal", "sha256"), "9" * 64),
        (("revision_namespace_files", "0", "mtime_ns"), 999),
        (("revision_namespace_files", "0", "sha256"), "9" * 64),
        (("shared_memory_after", "path"), "D:/other/source.sqlite-shm"),
        (("shared_memory_after", "bytes"), 32769),
        (("shared_memory_after", "sha256"), "9" * 64),
        (("source_generation",), 3),
        (("journal_mode",), "delete"),
    ],
)
def test_current_observed_cycle_reuse_rejects_non_mtime_source_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pin_path: tuple[str, ...],
    replacement: object,
) -> None:
    path, _digest, _ = _reuse_cycle_fixture(tmp_path, monkeypatch)
    reuse_terminal = json.loads(path.read_text(encoding="utf-8"))
    observation = reuse_terminal["same_run_pins"]["current_source_observation"]
    cursor: object = observation
    for segment in pin_path[:-1]:
        if isinstance(cursor, list):
            cursor = cursor[int(segment)]
        else:
            assert isinstance(cursor, dict)
            cursor = cursor[segment]
    if pin_path:
        if len(pin_path) == 1:
            assert isinstance(observation, dict)
            observation[pin_path[0]] = replacement
        else:
            assert isinstance(cursor, dict)
            cursor[pin_path[-1]] = replacement
    digest = _write_json_pin(path, reuse_terminal)

    with pytest.raises(ValueError, match="input identity differs: current_source_observation"):
        verify_current_observed_cycle_reuse(
            reuse_terminal_path=path,
            reuse_terminal_sha256=digest,
            expected_raw_run_id="raw-reuse",
            expected_source_date="2026-10-05",
        )


@pytest.mark.parametrize(
    ("mutation",),
    [
        ("missing_before",),
        ("missing_after",),
        ("missing_mtime",),
        ("bool_mtime",),
        ("text_mtime",),
        ("extra_pin_field",),
    ],
)
def test_current_observed_cycle_reuse_rejects_missing_or_malformed_shm_pins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    path, _digest, _ = _reuse_cycle_fixture(tmp_path, monkeypatch)
    reuse_terminal = json.loads(path.read_text(encoding="utf-8"))
    observation = reuse_terminal["same_run_pins"]["current_source_observation"]
    if mutation == "missing_before":
        observation.pop("shared_memory_before")
    elif mutation == "missing_after":
        observation.pop("shared_memory_after")
    elif mutation == "missing_mtime":
        observation["shared_memory_before"].pop("mtime_ns")
    elif mutation == "bool_mtime":
        observation["shared_memory_after"]["mtime_ns"] = True
    elif mutation == "text_mtime":
        observation["shared_memory_after"]["mtime_ns"] = "104"
    else:
        observation["shared_memory_after"]["unverified"] = True
    digest = _write_json_pin(path, reuse_terminal)

    with pytest.raises(ValueError, match="input identity differs: current_source_observation"):
        verify_current_observed_cycle_reuse(
            reuse_terminal_path=path,
            reuse_terminal_sha256=digest,
            expected_raw_run_id="raw-reuse",
            expected_source_date="2026-10-05",
        )


@pytest.mark.parametrize(
    ("replacement",),
    [
        ("sha256:" + "9" * 64,),
        ("sha256:" + "g" * 64,),
        ("a" * 63,),
        ("A" * 64,),
        (True,),
        (None,),
    ],
)
def test_current_observed_cycle_reuse_rejects_invalid_registry_record_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: object,
) -> None:
    path, _digest, _ = _reuse_cycle_fixture(tmp_path, monkeypatch)
    reuse_terminal = json.loads(path.read_text(encoding="utf-8"))
    reuse_terminal["reused_from"]["registry_record_sha256"] = replacement
    digest = _write_json_pin(path, reuse_terminal)

    with pytest.raises(ValueError, match="reused registry identity differs from original terminal"):
        verify_current_observed_cycle_reuse(
            reuse_terminal_path=path,
            reuse_terminal_sha256=digest,
            expected_raw_run_id="raw-reuse",
            expected_source_date="2026-10-05",
        )


def test_current_observed_cycle_reuse_rejects_registry_run_id_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _, registry_path = _reuse_cycle_fixture(
        tmp_path,
        monkeypatch,
        registry_run_id="registry-expected",
    )
    registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_payload["run_id"] = "registry-crossed"
    new_registry_hash = _write_json_pin(registry_path, registry_payload)
    research_root = registry_path.parents[3]
    cycles_root = research_root / "current_stock_cycles"
    original_terminal_path = cycles_root / "original" / "terminal_receipt.json"
    original_terminal = json.loads(original_terminal_path.read_text(encoding="utf-8"))
    original_terminal["registry"]["record_sha256"] = new_registry_hash
    original_terminal_sha = _write_json_pin(original_terminal_path, original_terminal)
    reuse_terminal = json.loads(path.read_text(encoding="utf-8"))
    reuse_terminal["reused_from"]["terminal_receipt_sha256"] = original_terminal_sha
    reuse_terminal["reused_from"]["registry_record_sha256"] = new_registry_hash
    _write_json_pin(path, reuse_terminal)

    with pytest.raises(ValueError, match="registry record semantics"):
        verify_current_observed_cycle_reuse(
            reuse_terminal_path=path,
            reuse_terminal_sha256=_file_sha256(path),
            expected_raw_run_id="raw-reuse",
            expected_source_date="2026-10-05",
        )

