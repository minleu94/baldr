from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from app_module.current_observed_source_contract import (
    build_current_observed_source_contract,
    _source_identities_stable,
)
import app_module.current_observed_source_contract as source_contract_module
from app_module.decision_market_frame import DecisionMarketFrameLoader
from app_module.exceptions import BacktestCancelledError


TAIPEI_TZ = timezone(timedelta(hours=8))
CUTOFF = datetime(2026, 10, 5, 8, 0, tzinfo=TAIPEI_TZ)
AS_OF = date(2026, 10, 5)


def _make_market_db(path: Path, *, include_times: bool = True) -> None:
    time_columns = ", available_at TEXT, observed_at TEXT" if include_times else ""
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE daily_prices ("
            '"日期" TEXT, "證券代號" TEXT, "收盤價" REAL, '
            '"漲跌價差" REAL, "成交股數" INTEGER' + time_columns + ")"
        )
        if include_times:
            rows = [
                (
                    "2026-10-02",
                    "2382",
                    100.0,
                    0.5,
                    100000,
                    "2026-10-05T07:00:00+08:00",
                    "2026-10-05T07:10:00+08:00",
                ),
                (
                    "20261002",
                    "2382",
                    100.1,
                    0.6,
                    120000,
                    "2026-10-05T07:00:00+08:00",
                    "2026-10-05T07:10:00+08:00",
                ),
                (
                    "2026-10-02",
                    "1477",
                    50.0,
                    0.1,
                    90000,
                    "2026-10-05T07:00:00+08:00",
                    "2026-10-05T08:01:00+08:00",
                ),
                (
                    "2026-10-03",
                    "1477",
                    50.5,
                    0.5,
                    95000,
                    "2026-10-05T08:01:00+08:00",
                    "2026-10-05T07:59:00+08:00",
                ),
                (
                    "2026-10-06",
                    "2382",
                    105.0,
                    4.9,
                    130000,
                    "2026-10-05T07:00:00+08:00",
                    "2026-10-05T07:10:00+08:00",
                ),
            ]
            connection.executemany(
                "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?)", rows
            )
        else:
            connection.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?)",
                ("2026-10-02", "2382", 100.0, 0.5, 100000),
            )


def _contract(path: Path, **overrides):
    options = {
        "decision_cutoff": CUTOFF,
        "as_of_date": AS_OF,
        "window_trading_days": 5,
        "symbols": ("2382", "1477"),
    }
    options.update(overrides)
    return build_current_observed_source_contract(path, **options)


def test_contract_keeps_explicit_cohort_separate_from_market_denominator_and_filters_cutoff(tmp_path):
    path = tmp_path / "prices.sqlite"
    _make_market_db(path)

    contract = _contract(path, symbols=("2382", "1477", "9999"))

    assert contract["status"] == "partial"
    assert contract["scope"]["denominator_known"] is True
    assert contract["scope"]["denominator"] == 3
    assert contract["scope"]["missing_symbols"] == ["9999"]
    assert contract["scope"]["market_universe_completeness"] == "unknown"
    assert contract["source"]["rowset"]["reader_rows_before_symbol_filter"] == 4
    assert contract["source"]["rowset"]["duplicate_symbol_market_date_rows"] == 1
    assert contract["source"]["rowset"]["rows_with_future_market_date"] == 0
    assert contract["source"]["rowset"]["cutoff_screened_rows"] == 2
    assert contract["source"]["source_time_fields"]["available_at_counts"]["known"] == 4
    assert contract["availability"]["historical_pit_eligible"] is False
    assert contract["availability"]["official_availability_verified"] is False
    assert contract["source"]["rowset"]["content_sha256"]
    windows = {item["symbol"]: item for item in contract["stock_windows"]}
    assert windows["2382"]["distinct_market_dates"] == 1
    assert windows["2382"]["row_count"] == 2
    assert windows["1477"]["last_market_date"] == "2026-10-03"
    assert windows["1477"]["cutoff_screened_rows"] == 0


def test_contract_allows_current_observed_rows_when_availability_is_unknown(tmp_path):
    path = tmp_path / "prices-no-clocks.sqlite"
    _make_market_db(path, include_times=False)

    contract = _contract(path, symbols=("2382",))

    assert contract["status"] == "observed"
    assert contract["source"]["rowset"]["scoped_rows"] == 1
    assert contract["source"]["source_time_fields"]["available_at_column_present"] is False
    assert contract["source"]["source_time_fields"]["available_at_counts"]["unknown"] == 1
    assert contract["source"]["rowset"]["cutoff_screened_rows"] == 0
    assert contract["availability"]["state"] == "unknown"
    assert contract["historical_pit_eligible"] is False
    assert contract["formal_training_eligible"] is False
    assert contract["published_snapshot"] is False


def test_cutoff_requires_aware_taipei_date_and_rejects_future_as_of(tmp_path):
    path = tmp_path / "prices.sqlite"
    _make_market_db(path)

    with pytest.raises(ValueError, match="時區"):
        _contract(path, decision_cutoff=datetime(2026, 10, 5, 8, 0))
    wrong_date = _contract(path, as_of_date=date(2026, 10, 4))
    assert wrong_date["status"] == "rejected"
    assert wrong_date["blockers"][0]["code"] == "as_of_date_mismatch"

    tomorrow = date.today() + timedelta(days=1)
    future_cutoff = datetime.combine(tomorrow, datetime.min.time(), tzinfo=TAIPEI_TZ)
    future = _contract(path, decision_cutoff=future_cutoff, as_of_date=tomorrow)
    assert future["status"] == "rejected"
    assert future["blockers"][0]["code"] == "future_as_of"

    with pytest.raises(ValueError, match="window_trading_days"):
        _contract(path, window_trading_days=2.9)


def test_explicit_source_and_scope_pins_and_rowset_content_change(tmp_path):
    path = tmp_path / "prices.sqlite"
    _make_market_db(path)
    first = _contract(path, symbols=("2382",))
    pin = first["source"]["file_identity_before"]

    matched = _contract(path, symbols=("2382",), expected_source_pin={"size_bytes": pin["size_bytes"]})
    wrong_source = _contract(path, symbols=("2382",), expected_source_pin={"size_bytes": -1})
    wrong_scope = _contract(path, symbols=("2382",), expected_scope_identity="symbols-sha256:wrong")

    assert matched["source"]["expected_pin_state"] == "matched"
    assert wrong_source["status"] == "rejected"
    assert wrong_source["blockers"][0]["code"] == "source_pin_mismatch"
    assert wrong_scope["status"] == "rejected"
    assert wrong_scope["blockers"][0]["code"] == "scope_identity_mismatch"

    with sqlite3.connect(path) as connection:
        connection.execute(
            'UPDATE daily_prices SET "收盤價" = 101.0 WHERE "證券代號" = ? AND "日期" = ?',
            ("2382", "2026-10-02"),
        )
    second = _contract(path, symbols=("2382",))
    assert first["source"]["rowset"]["content_sha256"] != second["source"]["rowset"]["content_sha256"]


def test_feature_warmup_and_benchmark_stay_unknown_without_evidence(tmp_path):
    path = tmp_path / "prices.sqlite"
    _make_market_db(path)
    feature = {
        "name": "MA20",
        "source_table": "technical_indicators",
        "columns": ["MA20"],
        "window_sessions": 5,
    }

    contract = _contract(path, feature_specs=(feature,))

    assert contract["features"]["state"] == "caller_declared"
    assert contract["features"]["items"][0]["computed"] is False
    assert contract["features"]["items"][0]["warmup_spec"]["state"] == "unknown"
    assert contract["features"]["items"][0]["warmup_spec"]["warmup_qualified"] is False
    assert contract["features"]["items"][0]["requested_columns_read"] is False
    assert contract["benchmark"]["state"] == "unknown"


def test_current_company_classification_never_becomes_historical_membership(tmp_path):
    path = tmp_path / "prices.sqlite"
    _make_market_db(path)
    companies = tmp_path / "companies.csv"
    companies.write_text(
        "stock_id,industry_category,stock_name,type,date,download_time\n"
        "2382,電腦及週邊設備業,Example,stock,2026-10-06,2026-10-06T10:00:00+08:00\n",
        encoding="utf-8",
    )

    contract = _contract(path, symbols=("2382",), company_classification_csv=companies)

    classification = contract["company_classification"]
    assert classification["state"] == "current_only_observed"
    assert classification["membership_semantics"] == "current_only"
    assert classification["historical_pit_eligible"] is False
    assert classification["rows_after_as_of_date"] == 1
    assert classification["cutoff_qualified_rows"] == 0
    assert classification["current_membership_used_for_historical_scope"] is False
    assert classification["rowset_sha256"]


def test_loader_optional_timing_projection_is_cache_isolated_and_legacy_shape_is_unchanged(tmp_path):
    path = tmp_path / "prices.sqlite"
    _make_market_db(path)
    loader = DecisionMarketFrameLoader(path)

    legacy = loader.load(AS_OF, 5)
    with_timing = loader.load(AS_OF, 5, include_source_timing=True)
    legacy_again = loader.load(AS_OF, 5)

    assert tuple(legacy.columns) == DecisionMarketFrameLoader.COLUMNS
    assert tuple(legacy_again.columns) == DecisionMarketFrameLoader.COLUMNS
    assert "available_at" not in legacy.columns
    assert with_timing.columns[-2:].tolist() == ["available_at", "observed_at"]
    assert with_timing.iloc[0]["available_at"] == "2026-10-05T07:00:00+08:00"


def test_strict_query_errors_are_named_but_legacy_loader_fallback_is_unchanged(tmp_path, monkeypatch):
    path = tmp_path / "prices.sqlite"
    _make_market_db(path)
    original_read_sql = pd.read_sql_query

    def fail_select(query, *args, **kwargs):
        if "SELECT DISTINCT" in query:
            raise sqlite3.OperationalError("fixture SQL failure")
        return original_read_sql(query, *args, **kwargs)

    monkeypatch.setattr(pd, "read_sql_query", fail_select)
    loader = DecisionMarketFrameLoader(path)
    assert loader.load(AS_OF, 5).empty
    with pytest.raises(sqlite3.OperationalError, match="fixture SQL failure"):
        loader.load(AS_OF, 5, raise_sql_errors=True)

    contract = _contract(path)
    assert contract["status"] == "rejected"
    assert contract["blockers"][0]["code"] == "source_query_failed"
    assert contract["source"]["query_error_type"] == "OperationalError"


def test_contract_propagates_cancellation_and_source_identity_guard_marks_shm_mtime_only(tmp_path):
    path = tmp_path / "prices.sqlite"
    _make_market_db(path)
    with pytest.raises(BacktestCancelledError):
        _contract(path, cancel_callback=lambda: True)

    before = {
        "path": "db",
        "device": 1,
        "inode": 2,
        "size_bytes": 3,
        "mtime_ns": 4,
        "wal": None,
        "shm": {"path": "db-shm", "device": 1, "inode": 5, "size_bytes": 6, "mtime_ns": 7},
    }
    after = {
        **before,
        "shm": {"path": "db-shm", "device": 1, "inode": 5, "size_bytes": 6, "mtime_ns": 8},
    }
    assert _source_identities_stable(before, after) == (True, True)
    after["wal"] = {"path": "db-wal", "size_bytes": 9, "mtime_ns": 10}
    assert _source_identities_stable(before, after)[0] is False


def test_changed_source_rejection_retains_after_identity_and_schema_summary(tmp_path, monkeypatch):
    path = tmp_path / "prices.sqlite"
    _make_market_db(path)
    original_identity = source_contract_module._file_identity
    calls = 0

    def identity_with_new_wal(source_path):
        nonlocal calls
        calls += 1
        identity = original_identity(source_path)
        if calls == 2:
            identity = dict(identity)
            identity["wal"] = {
                "path": f"{source_path}-wal",
                "size_bytes": 0,
                "mtime_ns": 123,
            }
        return identity

    monkeypatch.setattr(source_contract_module, "_file_identity", identity_with_new_wal)
    contract = _contract(path)

    assert contract["status"] == "rejected"
    assert contract["blockers"][0]["code"] == "source_changed_during_read"
    assert contract["source"]["file_identity_after"]["wal"]["size_bytes"] == 0
    assert contract["source"]["schema_sha256_after"]
    assert "wal.identity" in contract["source"]["identity_differences"]


def test_cli_writes_utf8_json_to_stdout_under_legacy_console_encoding(tmp_path):
    path = tmp_path / "prices.sqlite"
    _make_market_db(path, include_times=False)
    script = Path(__file__).resolve().parents[1] / "scripts" / "inspect_current_observed_source_contract.py"
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252"
    env.pop("PYTHONUTF8", None)

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db-path",
            str(path),
            "--decision-cutoff",
            "2026-10-05T08:00:00+08:00",
            "--as-of-date",
            "2026-10-05",
            "--window-trading-days",
            "2",
            "--symbols",
            "2382",
        ],
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    output = result.stdout.decode("utf-8")
    assert '"status": "observed"' in output
    assert "來源" in output
    assert "current-observed-source-contract.v1" in output


def test_cli_rejects_invalid_json_payload_type_without_traceback(tmp_path):
    path = tmp_path / "prices.sqlite"
    _make_market_db(path, include_times=False)
    feature_spec = tmp_path / "feature-spec.json"
    feature_spec.write_text("42", encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "inspect_current_observed_source_contract.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db-path",
            str(path),
            "--decision-cutoff",
            "2026-10-05T08:00:00+08:00",
            "--as-of-date",
            "2026-10-05",
            "--window-trading-days",
            "2",
            "--feature-spec-file",
            str(feature_spec),
        ],
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    output = result.stdout.decode("utf-8")
    assert '"code": "invalid_request"' in output
    assert "Traceback" not in output
