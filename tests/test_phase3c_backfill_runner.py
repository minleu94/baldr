from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from data_module import phase3c_backfill_runner as runner_module
from data_module.p0_candidate_repository import ProductionPathRejectedError
from data_module.phase3c_backfill_runner import APPLY_CONFIRM_TOKEN, Phase3CBackfillRunner
from scripts.update_phase3c_candidates import update_phase3c_candidates_range
import scripts.update_phase3c_candidates as candidates_script
import app_module.update_service as update_service_module


def _production_db(tmp_path):
    prod_root = tmp_path / "FA_Data"
    prod_db = prod_root / "sqlite" / "twstock.db"
    prod_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(prod_db) as conn:
        conn.execute("CREATE TABLE market_indices (trade_date TEXT, index_name TEXT)")
        conn.execute("INSERT INTO market_indices VALUES ('20240722', 'TAIEX')")
    return prod_root, prod_db


def _institutional_frame():
    return pd.DataFrame([{
        "stock_code": "2330", "decision_date": "2024-07-22", "source_version": "test-v1",
        "publication_at": None, "first_observed_at": "2024-07-22T10:00:00Z",
        "available_at": "2024-07-22T10:00:00Z", "available_date": None, "quality": "degraded",
        "foreign_investor_buy": 100, "foreign_investor_sell": 50, "foreign_investor_net": 50,
        "investment_trust_buy": 10, "investment_trust_sell": 5, "investment_trust_net": 5,
        "dealer_buy": 20, "dealer_sell": 10, "dealer_net": 10,
    }])


def _institutional_frame_two_rows():
    second = _institutional_frame().copy()
    second.loc[0, "stock_code"] = "2317"
    second.loc[0, "foreign_investor_buy"] = 80
    second.loc[0, "foreign_investor_sell"] = 30
    second.loc[0, "foreign_investor_net"] = 50
    return pd.concat([_institutional_frame(), second], ignore_index=True)


def _credit_frame():
    return pd.DataFrame([{
        "stock_code": "2330", "decision_date": "2024-07-22", "source_version": "test-v1",
        "publication_at": None, "first_observed_at": "2024-07-22T10:00:00Z",
        "available_at": "2024-07-22T10:00:00Z", "available_date": None, "quality": "degraded",
        "margin_purchase": 100, "margin_balance": 200, "short_sale": 10, "short_balance": 20,
        "financing": None, "securities_lending": None,
    }])


def _seed_source_rows(
    runner: Phase3CBackfillRunner,
    candidate_db: Path,
    source: str,
    frame: pd.DataFrame,
    *,
    checkpoint_status: str | None = "FAILED_RETRYABLE",
):
    table_name = {
        "institutional": "institutional_flows",
        "credit": "credit_transactions",
    }[source]
    with sqlite3.connect(candidate_db) as conn:
        runner._ensure_candidate_tables(conn)
        frame.to_sql(table_name, conn, if_exists="append", index=False)
        if checkpoint_status is not None:
            conn.execute(
                """
                INSERT INTO phase3c_backfill_checkpoints (
                    decision_date, source, status, row_count, fetched_at, error_message
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "2024-07-22",
                    source,
                    checkpoint_status,
                    0,
                    "2024-07-22T10:00:00+00:00",
                    "seeded fixture checkpoint",
                ),
            )


def _tdcc_frame():
    return pd.DataFrame([{
        "stock_code": "2330", "decision_date": "2024-07-19", "source_version": "test-v1",
        "publication_at": None, "first_observed_at": "2024-07-22T10:00:00Z",
        "available_at": "2024-07-22T10:00:00Z", "available_date": None, "quality": "degraded",
        "shareholding_tiers": "weekly_distribution_available",
        "large_holder_ratio_bp": 6000, "retail_holder_ratio_bp": 1200,
        "dispersion_index_bp": -4800,
    }])


def test_runner_rejects_production_db_path(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    with pytest.raises(ProductionPathRejectedError):
        Phase3CBackfillRunner(prod_db, production_data_root=prod_root, production_db_path=prod_db)


def test_runner_rejects_unknown_source(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    with pytest.raises(ValueError, match="sources 必須"):
        Phase3CBackfillRunner(
            tmp_path / "candidate.db", sources=("unknown",),
            production_data_root=prod_root, production_db_path=prod_db,
        )


def test_apply_requires_explicit_candidate_db_path():
    with pytest.raises(ValueError, match="explicit --db-path"):
        update_phase3c_candidates_range(
            "2024-07-22", "2024-07-22", dry_run=False, db_path=None
        )


def test_configured_candidate_db_uses_persisted_user_environment_when_process_is_stale(
    tmp_path,
    monkeypatch,
):
    candidate = tmp_path / "candidate.db"
    monkeypatch.delenv("PHASE3C_CANDIDATE_DB_PATH", raising=False)
    monkeypatch.setattr(
        runner_module,
        "_persisted_user_environment_value",
        lambda _name: str(candidate),
    )

    assert runner_module.configured_candidate_db_path() == candidate


def test_process_candidate_environment_overrides_persisted_user_value(
    tmp_path,
    monkeypatch,
):
    process_candidate = tmp_path / "process.db"
    monkeypatch.setenv(
        "PHASE3C_CANDIDATE_DB_PATH",
        str(process_candidate),
    )
    monkeypatch.setattr(
        runner_module,
        "_persisted_user_environment_value",
        lambda _name: str(tmp_path / "persisted.db"),
    )

    assert runner_module.configured_candidate_db_path() == process_candidate


def test_runner_dry_run_leaves_candidate_db_untouched(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    cand_db = tmp_path / "candidate.db"
    runner = Phase3CBackfillRunner(
        cand_db, sources=("institutional",), production_data_root=prod_root,
        production_db_path=prod_db, rate_limit_seconds=0,
    )
    with patch("data_module.phase3c_backfill_runner.fetch_institutional_flows", return_value=_institutional_frame()):
        summary = runner.run_backfill(date(2024, 7, 22), date(2024, 7, 22), dry_run=True)

    assert summary.succeeded_days_count == 1
    assert not cand_db.exists()


def test_runner_blocks_unknown_calendar_and_retries_after_calendar_recovers(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    candidate_db = tmp_path / "candidate.db"

    class _Calendar:
        state = None

        def get_trading_days_in_range(self, start, end, *, allow_online_probe):
            assert start == end == date(2024, 7, 22)
            assert allow_online_probe is False
            return [{
                "date": start,
                "date_str": start.isoformat(),
                "is_trading_day": self.state,
                "reason_code": "test_calendar_unavailable" if self.state is None else "test_open",
            }]

    calendar = _Calendar()
    phase3c_runner = Phase3CBackfillRunner(
        candidate_db,
        sources=("institutional",),
        production_data_root=prod_root,
        production_db_path=prod_db,
        rate_limit_seconds=0,
        allow_online_calendar_probe=False,
        calendar=calendar,
    )
    with patch(
        "data_module.phase3c_backfill_runner.fetch_institutional_flows",
        return_value=_institutional_frame(),
    ) as fetch:
        unresolved = phase3c_runner.run_backfill(
            date(2024, 7, 22), date(2024, 7, 22), dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )
        fetch.assert_not_called()
        assert unresolved.failed_days_count == 1
        assert unresolved.skipped_days_count == 0
        assert unresolved.daily_results[0]["status"] == "BLOCKED_CALENDAR_UNKNOWN"
        assert "2024-07-22" in unresolved.daily_results[0]["error_message"]
        with sqlite3.connect(candidate_db) as conn:
            checkpoint = conn.execute(
                "SELECT status FROM phase3c_backfill_checkpoints "
                "WHERE decision_date='2024-07-22' AND source='institutional'"
            ).fetchone()
        assert checkpoint == ("BLOCKED_CALENDAR_UNKNOWN",)

        calendar.state = True
        recovered = phase3c_runner.run_backfill(
            date(2024, 7, 22), date(2024, 7, 22), dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )

    assert fetch.call_count == 1
    assert recovered.failed_days_count == 0
    assert recovered.daily_results[0]["status"] == "SUCCESS"


def test_runner_keeps_verified_market_closure_as_a_skip_without_fetch(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)

    class _Calendar:
        def get_trading_days_in_range(self, start, end, *, allow_online_probe):
            assert allow_online_probe is False
            return [{
                "date": start,
                "date_str": start.isoformat(),
                "is_trading_day": False,
                "reason_code": "test_official_closure",
            }]

    phase3c_runner = Phase3CBackfillRunner(
        tmp_path / "candidate.db",
        sources=("institutional", "credit"),
        production_data_root=prod_root,
        production_db_path=prod_db,
        rate_limit_seconds=0,
        allow_online_calendar_probe=False,
        calendar=_Calendar(),
    )
    with patch("data_module.phase3c_backfill_runner.fetch_institutional_flows") as institutional, patch(
        "data_module.phase3c_backfill_runner.fetch_credit_transactions"
    ) as credit:
        summary = phase3c_runner.run_backfill(
            date(2024, 7, 22), date(2024, 7, 22), dry_run=True
        )

    institutional.assert_not_called()
    credit.assert_not_called()
    assert summary.failed_days_count == 0
    assert summary.skipped_days_count == 2
    assert {item["status"] for item in summary.daily_results} == {
        "SKIPPED_NOT_TRADING_DAY"
    }


def test_phase3c_range_wrapper_passes_caller_calendar_and_offline_policy(
    tmp_path, monkeypatch
):
    calendar = object()
    observed = {}

    class _Runner:
        def __init__(self, **kwargs):
            observed.update(kwargs)

        def run_backfill(self, **_kwargs):
            return SimpleNamespace(
                failed_days_count=0,
                total_days=1,
                succeeded_days_count=1,
                skipped_days_count=0,
                daily_results=[],
            )

    monkeypatch.setattr(candidates_script, "Phase3CBackfillRunner", _Runner)
    result = update_phase3c_candidates_range(
        start_date="2024-07-22",
        end_date="2024-07-22",
        dry_run=True,
        sources=("institutional",),
        allow_online_calendar_probe=False,
        calendar=calendar,
    )

    assert result["success"] is True
    assert observed["calendar"] is calendar
    assert observed["allow_online_calendar_probe"] is False


def test_candidate_cli_explicit_calendar_cache_is_validated_and_forces_offline(
    tmp_path, monkeypatch
):
    cache_path = tmp_path / "calendar_cache"
    cache_path.mkdir()
    observed = {}

    class _Calendar:
        def __init__(self, *, calendar_cache_path):
            observed["calendar_cache_path"] = calendar_cache_path

        def _load_cached_year_schedule(self, calendar_year):
            observed.setdefault("years", []).append(calendar_year)
            return object()

    monkeypatch.setattr(candidates_script, "OfficialTradingCalendar", _Calendar)
    calendar = candidates_script._calendar_for_candidate_cli(
        cache_path,
        "2025-12-31",
        "2026-01-02",
    )

    assert isinstance(calendar, _Calendar)
    assert observed["calendar_cache_path"] == cache_path.resolve()
    assert observed["years"] == [2025, 2026]


@pytest.mark.parametrize(
    ("status", "failed_days", "skipped_days", "expected_exit_code"),
    [
        ("SKIPPED_NOT_TRADING_DAY", 0, 1, 0),
        ("FAILED_RETRYABLE", 1, 0, 2),
        ("BLOCKED_CALENDAR_UNKNOWN", 1, 0, 2),
    ],
)
def test_candidate_cli_exit_code_tracks_no_work_and_retryable_calendar_results(
    tmp_path,
    monkeypatch,
    status,
    failed_days,
    skipped_days,
    expected_exit_code,
):
    class _Runner:
        def __init__(self, **_kwargs):
            pass

        def run_backfill(self, **_kwargs):
            return SimpleNamespace(
                failed_days_count=failed_days,
                total_days=1,
                succeeded_days_count=0,
                skipped_days_count=skipped_days,
                daily_results=[{
                    "decision_date": "2024-07-22",
                    "source": "institutional",
                    "status": status,
                }],
            )

    monkeypatch.setattr(candidates_script, "Phase3CBackfillRunner", _Runner)
    monkeypatch.chdir(tmp_path)

    exit_code = candidates_script.main(
        ["--date", "2024-07-22", "--sources", "institutional"]
    )

    assert exit_code == expected_exit_code


def test_phase3c_range_wrapper_reports_unknown_calendar_dates_as_failure(
    monkeypatch,
):
    class _Runner:
        def __init__(self, **_kwargs):
            pass

        def run_backfill(self, **_kwargs):
            return SimpleNamespace(
                failed_days_count=1,
                total_days=1,
                succeeded_days_count=0,
                skipped_days_count=0,
                daily_results=[{
                    "decision_date": "2024-07-22",
                    "source": "institutional",
                    "status": "BLOCKED_CALENDAR_UNKNOWN",
                }],
            )

    monkeypatch.setattr(candidates_script, "Phase3CBackfillRunner", _Runner)
    result = update_phase3c_candidates_range(
        start_date="2024-07-22",
        end_date="2024-07-22",
        dry_run=True,
        sources=("institutional",),
    )

    assert result["success"] is False
    assert "2024-07-22" in result["message"]


def test_phase3c_range_wrapper_preserves_cancelled_partial_summary(monkeypatch):
    summary = SimpleNamespace(
        failed_days_count=0,
        cancelled=True,
        total_days=4,
        succeeded_days_count=2,
        skipped_days_count=0,
        daily_results=[{"status": "SUCCESS"}, {"status": "SUCCESS"}],
    )

    class _Runner:
        def __init__(self, **_kwargs):
            pass

        def run_backfill(self, **_kwargs):
            return summary

    monkeypatch.setattr(candidates_script, "Phase3CBackfillRunner", _Runner)
    result = update_phase3c_candidates_range(
        start_date="2024-07-22",
        end_date="2024-07-25",
        dry_run=True,
        sources=("institutional",),
    )

    assert result["success"] is False
    assert result["cancelled"] is True
    assert result["summary"] is summary
    assert "已完成 2 天" in result["message"]


def test_update_service_passes_calendar_to_phase3c_range(
    tmp_path, monkeypatch
):
    candidate_db = tmp_path / "candidate.db"
    calendar = object()
    cancel_callback = lambda: False
    observed = {}

    def _update_range(**kwargs):
        observed.update(kwargs)
        return {"success": True, "summary": object(), "message": "ok"}

    monkeypatch.setattr(
        update_service_module,
        "configured_candidate_db_path",
        lambda: candidate_db,
    )
    monkeypatch.setattr(
        candidates_script,
        "update_phase3c_candidates_range",
        _update_range,
    )
    service = update_service_module.UpdateService(
        SimpleNamespace(meta_data_dir=tmp_path / "meta_data")
    )

    result = service.update_phase3c_candidate_range(
        start_date="2024-07-22",
        end_date="2024-07-22",
        allow_online_calendar_probe=False,
        calendar=calendar,
        cancel_callback=cancel_callback,
    )

    assert result["success"] is True
    assert observed["calendar"] is calendar
    assert observed["allow_online_calendar_probe"] is False
    assert observed["cancel_callback"] is cancel_callback


def test_runner_sources_filter_excludes_tdcc_and_writes_checkpoints(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    cand_db = tmp_path / "candidate.db"
    runner = Phase3CBackfillRunner(
        cand_db, sources=("institutional", "credit"), production_data_root=prod_root,
        production_db_path=prod_db, rate_limit_seconds=0,
    )
    with patch("data_module.phase3c_backfill_runner.fetch_institutional_flows", return_value=_institutional_frame()) as institutional, patch(
        "data_module.phase3c_backfill_runner.fetch_credit_transactions", return_value=_credit_frame()
    ) as credit:
        summary = runner.run_backfill(
            date(2024, 7, 22), date(2024, 7, 22), dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )

    assert {r["source"] for r in summary.daily_results} == {"institutional", "credit"}
    assert institutional.call_count == 1
    assert credit.call_count == 1
    with sqlite3.connect(cand_db) as conn:
        checkpoints = conn.execute(
            "SELECT source, status FROM phase3c_backfill_checkpoints ORDER BY source"
        ).fetchall()
    assert checkpoints == [("credit", "SUCCESS"), ("institutional", "SUCCESS")]


def test_runner_resume_uses_success_checkpoint_without_refetch(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    runner = Phase3CBackfillRunner(
        tmp_path / "candidate.db", sources=("institutional",), production_data_root=prod_root,
        production_db_path=prod_db, rate_limit_seconds=0,
    )
    with patch("data_module.phase3c_backfill_runner.fetch_institutional_flows", return_value=_institutional_frame()) as fetch:
        runner.run_backfill(date(2024, 7, 22), date(2024, 7, 22), dry_run=False, confirm_token=APPLY_CONFIRM_TOKEN)
        resumed = runner.run_backfill(date(2024, 7, 22), date(2024, 7, 22), dry_run=False, confirm_token=APPLY_CONFIRM_TOKEN)

    assert fetch.call_count == 1
    assert resumed.daily_results[0]["status"] == "SKIPPED_ALREADY_EXISTS"


@pytest.mark.parametrize(
    ("source", "frame_factory", "fetch_name"),
    [
        ("institutional", _institutional_frame, "fetch_institutional_flows"),
        ("credit", _credit_frame, "fetch_credit_transactions"),
    ],
)
def test_runner_reconciles_failed_checkpoint_when_existing_rows_match(
    tmp_path, source, frame_factory, fetch_name
):
    prod_root, prod_db = _production_db(tmp_path)
    candidate_db = tmp_path / f"{source}.db"
    frame = frame_factory()
    runner = Phase3CBackfillRunner(
        candidate_db,
        sources=(source,),
        production_data_root=prod_root,
        production_db_path=prod_db,
        rate_limit_seconds=0,
    )
    _seed_source_rows(runner, candidate_db, source, frame)

    with patch(
        f"data_module.phase3c_backfill_runner.{fetch_name}",
        return_value=frame,
    ) as fetch:
        summary = runner.run_backfill(
            date(2024, 7, 22),
            date(2024, 7, 22),
            dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )

    result = summary.daily_results[0]
    assert fetch.call_count == 1
    assert result["status"] == "SUCCESS"
    assert summary.total_rows_inserted == 0
    assert result["reconciliation"]["status"] == "RECONCILED"
    assert result["reconciliation"]["matched_row_count"] == 1
    assert result["reconciliation"]["missing_key_count"] == 0
    assert result["reconciliation"]["inserted_row_count"] == 0
    with sqlite3.connect(candidate_db) as conn:
        checkpoint = conn.execute(
            "SELECT status, row_count FROM phase3c_backfill_checkpoints "
            "WHERE decision_date = '2024-07-22' AND source = ?",
            (source,),
        ).fetchone()
        row_count = conn.execute(
            f"SELECT COUNT(*) FROM {('institutional_flows' if source == 'institutional' else 'credit_transactions')} "
            "WHERE decision_date = '2024-07-22'"
        ).fetchone()[0]
    assert checkpoint == ("SUCCESS", 1)
    assert row_count == 1


def test_runner_does_not_use_row_presence_as_legacy_completion_shortcut(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    candidate_db = tmp_path / "candidate.db"
    frame = _institutional_frame()
    runner = Phase3CBackfillRunner(
        candidate_db,
        sources=("institutional",),
        production_data_root=prod_root,
        production_db_path=prod_db,
        rate_limit_seconds=0,
    )
    _seed_source_rows(
        runner,
        candidate_db,
        "institutional",
        frame,
        checkpoint_status=None,
    )

    with patch(
        "data_module.phase3c_backfill_runner.fetch_institutional_flows",
        return_value=frame,
    ) as fetch:
        summary = runner.run_backfill(
            date(2024, 7, 22),
            date(2024, 7, 22),
            dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )

    assert fetch.call_count == 1
    assert summary.daily_results[0]["status"] == "SUCCESS"
    assert summary.daily_results[0]["status"] != "SKIPPED_ALREADY_EXISTS"
    assert summary.daily_results[0]["reconciliation"]["matched_row_count"] == 1


def test_runner_reconciliation_starts_under_immediate_transaction(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    candidate_db = tmp_path / "candidate.db"
    frame = _institutional_frame()
    runner = Phase3CBackfillRunner(
        candidate_db,
        sources=("institutional",),
        production_data_root=prod_root,
        production_db_path=prod_db,
        rate_limit_seconds=0,
    )
    transaction_states = []
    original_reconcile = runner._reconcile_source_frame

    def wrapped_reconcile(conn, *args):
        transaction_states.append(conn.in_transaction)
        return original_reconcile(conn, *args)

    with patch.object(
        runner, "_reconcile_source_frame", side_effect=wrapped_reconcile
    ), patch(
        "data_module.phase3c_backfill_runner.fetch_institutional_flows",
        return_value=frame,
    ):
        summary = runner.run_backfill(
            date(2024, 7, 22),
            date(2024, 7, 22),
            dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )

    assert summary.daily_results[0]["status"] == "SUCCESS"
    assert transaction_states == [True]


@pytest.mark.parametrize(
    ("existing_value", "incoming_value"),
    [
        ("2026-09-03", "2026-09-17"),
        ("2026-09-03T00:00:00", "2026-09-17T00:00:00+00:00"),
        ("2026-09-03T00:00:00+00:00", "2026-09-17T00:00:00"),
        ("2026-09-17T00:00:00+00:00", "2026-09-16T00:00:00+00:00"),
    ],
)
def test_observation_clock_requires_timezone_aware_timestamps(
    existing_value, incoming_value
):
    assert not Phase3CBackfillRunner._observation_timestamp_is_monotonic(
        existing_value, incoming_value
    )


def test_runner_records_observation_at_after_slow_fetch(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    candidate_db = tmp_path / "candidate.db"
    existing = _institutional_frame()
    incoming_observed_at = None
    runner = Phase3CBackfillRunner(
        candidate_db,
        sources=("institutional",),
        production_data_root=prod_root,
        production_db_path=prod_db,
        rate_limit_seconds=0,
    )
    _seed_source_rows(runner, candidate_db, "institutional", existing)

    def slow_fetch(_decision_date):
        nonlocal incoming_observed_at
        incoming_observed_at = datetime.now(timezone.utc)
        time.sleep(0.03)
        incoming = existing.copy()
        incoming["first_observed_at"] = incoming_observed_at.isoformat()
        incoming["available_at"] = incoming_observed_at.isoformat()
        return incoming

    with patch(
        "data_module.phase3c_backfill_runner.fetch_institutional_flows",
        side_effect=slow_fetch,
    ):
        summary = runner.run_backfill(
            date(2024, 7, 22),
            date(2024, 7, 22),
            dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )

    assert incoming_observed_at is not None
    result = summary.daily_results[0]
    report = result["reconciliation"]
    observation_at = datetime.fromisoformat(report["observation_at"])
    assert result["status"] == "SUCCESS"
    assert observation_at >= incoming_observed_at
    assert report["observation_timing_error"] is None
    assert report["observation_mode"] == "new_observation_reconciled"
    with sqlite3.connect(candidate_db) as conn:
        preserved = conn.execute(
            "SELECT first_observed_at, available_at FROM institutional_flows "
            "WHERE stock_code = '2330' AND decision_date = '2024-07-22'"
        ).fetchone()
    assert preserved == ("2024-07-22T10:00:00Z", "2024-07-22T10:00:00Z")


def test_runner_rejects_observation_at_before_incoming_custody(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    candidate_db = tmp_path / "candidate.db"
    incoming = _institutional_frame()
    future_observed_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    incoming["first_observed_at"] = future_observed_at.isoformat()
    incoming["available_at"] = future_observed_at.isoformat()
    runner = Phase3CBackfillRunner(
        candidate_db,
        sources=("institutional",),
        production_data_root=prod_root,
        production_db_path=prod_db,
        rate_limit_seconds=0,
    )

    with patch(
        "data_module.phase3c_backfill_runner.fetch_institutional_flows",
        return_value=incoming,
    ):
        summary = runner.run_backfill(
            date(2024, 7, 22),
            date(2024, 7, 22),
            dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )

    result = summary.daily_results[0]
    report = result["reconciliation"]
    assert result["status"] == "FAILED_RETRYABLE"
    assert report["status"] == "CONFLICT"
    assert "observation_at" in report["observation_timing_error"]
    assert "observation_at" in result["error_message"]
    with sqlite3.connect(candidate_db) as conn:
        row_count = conn.execute(
            "SELECT COUNT(*) FROM institutional_flows "
            "WHERE decision_date = '2024-07-22'"
        ).fetchone()[0]
        checkpoint = conn.execute(
            "SELECT status FROM phase3c_backfill_checkpoints "
            "WHERE decision_date = '2024-07-22' AND source = 'institutional'"
        ).fetchone()[0]
        observation_mode = conn.execute(
            "SELECT observation_mode FROM phase3c_source_observations "
            "WHERE source = 'institutional' AND decision_date = '2024-07-22'"
        ).fetchone()[0]
    assert row_count == 0
    assert checkpoint == "FAILED_RETRYABLE"
    assert observation_mode == "conflict"


def test_runner_preserves_first_observation_for_newer_reobservation(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    candidate_db = tmp_path / "candidate.db"
    existing = _institutional_frame()
    incoming = existing.copy()
    incoming["first_observed_at"] = "2024-07-23T10:00:00+00:00"
    incoming["available_at"] = "2024-07-23T10:00:00+00:00"
    runner = Phase3CBackfillRunner(
        candidate_db,
        sources=("institutional",),
        production_data_root=prod_root,
        production_db_path=prod_db,
        rate_limit_seconds=0,
    )
    _seed_source_rows(runner, candidate_db, "institutional", existing)

    with patch(
        "data_module.phase3c_backfill_runner.fetch_institutional_flows",
        return_value=incoming,
    ):
        summary = runner.run_backfill(
            date(2024, 7, 22),
            date(2024, 7, 22),
            dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )

    result = summary.daily_results[0]
    assert result["status"] == "SUCCESS"
    assert result["reconciliation"]["observation_mode"] == "new_observation_reconciled"
    assert result["reconciliation"]["exact_match_row_count"] == 0
    assert result["reconciliation"]["new_observation_match_row_count"] == 1
    assert result["reconciliation"]["inserted_row_count"] == 0
    with sqlite3.connect(candidate_db) as conn:
        preserved = conn.execute(
            "SELECT first_observed_at, available_at FROM institutional_flows "
            "WHERE stock_code = '2330' AND decision_date = '2024-07-22'"
        ).fetchone()
        observation = conn.execute(
            "SELECT observation_mode, first_observed_at_min, available_at_max, "
            "observation_hash, canonical_payload_json "
            "FROM phase3c_source_observations "
            "WHERE source = 'institutional' AND decision_date = '2024-07-22'"
        ).fetchone()
    assert preserved == ("2024-07-22T10:00:00Z", "2024-07-22T10:00:00Z")
    assert observation[:3] == (
        "new_observation_reconciled",
        "2024-07-23T10:00:00+00:00",
        "2024-07-23T10:00:00+00:00",
    )
    observation_hash = observation[3]
    canonical_payload_json = observation[4]
    assert observation_hash == (
        "sha256:" + hashlib.sha256(canonical_payload_json.encode("utf-8")).hexdigest()
    )
    canonical_payload = json.loads(canonical_payload_json)
    assert canonical_payload["schema_version"] == "phase3c-canonical-observation.v1"
    assert canonical_payload["rows"][0]["first_observed_at"] == (
        "2024-07-23T10:00:00+00:00"
    )


def test_runner_reconciles_known_failed_checkpoint_scope_in_isolated_copy(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    candidate_db = tmp_path / "known-failed-scope.db"
    affected = [
        ("2026-09-03", "institutional"),
        ("2026-09-03", "credit"),
        ("2026-09-04", "institutional"),
        ("2026-09-04", "credit"),
        ("2026-09-07", "institutional"),
        ("2026-09-07", "credit"),
        ("2026-09-08", "institutional"),
        ("2026-09-08", "credit"),
        ("2026-09-09", "institutional"),
        ("2026-09-09", "credit"),
        ("2026-09-10", "institutional"),
        ("2026-09-10", "credit"),
        ("2026-09-11", "institutional"),
    ]
    trading_dates = sorted({day for day, _source in affected})
    runner = Phase3CBackfillRunner(
        candidate_db,
        sources=("institutional", "credit"),
        production_data_root=prod_root,
        production_db_path=prod_db,
        rate_limit_seconds=0,
    )

    def frame_for(source: str, day: str, hour: str) -> pd.DataFrame:
        frame = (_institutional_frame() if source == "institutional" else _credit_frame()).copy()
        frame["decision_date"] = day
        frame["first_observed_at"] = f"{day}T{hour}:00:00+00:00"
        frame["available_at"] = f"{day}T{hour}:00:00+00:00"
        return frame

    with sqlite3.connect(candidate_db) as conn:
        runner._ensure_candidate_tables(conn)
        for day, source in affected:
            frame = frame_for(source, day, "10")
            table_name = (
                "institutional_flows" if source == "institutional" else "credit_transactions"
            )
            frame.to_sql(table_name, conn, if_exists="append", index=False)
            conn.execute(
                """
                INSERT INTO phase3c_backfill_checkpoints (
                    decision_date, source, status, row_count, fetched_at, error_message
                ) VALUES (?, ?, 'FAILED_RETRYABLE', 0, ?, ?)
                """,
                (
                    day,
                    source,
                    "2026-09-16T11:30:00+00:00",
                    "UNIQUE constraint failed: fixture natural key",
                ),
            )

    trading_days = [
        {
            "date": date.fromisoformat(day),
            "date_str": day,
            "is_trading_day": True,
            "reason_code": "fixture_official_session",
        }
        for day in trading_dates
    ]
    with (
        patch.object(
            runner.calendar,
            "get_trading_days_in_range",
            return_value=trading_days,
        ),
        patch(
            "data_module.phase3c_backfill_runner.fetch_institutional_flows",
            side_effect=lambda day: frame_for("institutional", day.isoformat(), "11"),
        ),
        patch(
            "data_module.phase3c_backfill_runner.fetch_credit_transactions",
            side_effect=lambda day: frame_for("credit", day.isoformat(), "11"),
        ),
    ):
        summary = runner.run_backfill(
            date(2026, 9, 3),
            date(2026, 9, 11),
            dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )

    assert len(summary.daily_results) == 14
    assert summary.failed_days_count == 0
    assert summary.succeeded_days_count == 14
    assert summary.total_rows_inserted == 1
    assert sum(
        result["reconciliation"]["observation_mode"] == "new_observation_reconciled"
        for result in summary.daily_results
        if result["reconciliation"] is not None
    ) == 13
    with sqlite3.connect(candidate_db) as conn:
        failed_count = conn.execute(
            "SELECT COUNT(*) FROM phase3c_backfill_checkpoints "
            "WHERE decision_date >= '2026-09-03' AND status = 'FAILED_RETRYABLE'"
        ).fetchone()[0]
        success_count = conn.execute(
            "SELECT COUNT(*) FROM phase3c_backfill_checkpoints "
            "WHERE decision_date >= '2026-09-03' AND status = 'SUCCESS'"
        ).fetchone()[0]
        observations = conn.execute(
            "SELECT observation_mode, COUNT(*) FROM phase3c_source_observations "
            "WHERE decision_date >= '2026-09-03' GROUP BY observation_mode"
        ).fetchall()
        preserved = conn.execute(
            "SELECT first_observed_at, available_at FROM institutional_flows "
            "WHERE stock_code = '2330' AND decision_date = '2026-09-03'"
        ).fetchone()
    assert failed_count == 0
    assert success_count == 14
    assert sorted(observations) == [
        ("new_observation_insert", 1),
        ("new_observation_reconciled", 13),
    ]
    assert preserved == ("2026-09-03T10:00:00+00:00", "2026-09-03T10:00:00+00:00")


def test_runner_reconciles_partial_coverage_without_overwriting_existing_rows(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    candidate_db = tmp_path / "candidate.db"
    frame = _institutional_frame_two_rows()
    runner = Phase3CBackfillRunner(
        candidate_db,
        sources=("institutional",),
        production_data_root=prod_root,
        production_db_path=prod_db,
        rate_limit_seconds=0,
    )
    _seed_source_rows(
        runner,
        candidate_db,
        "institutional",
        frame.iloc[[0]],
    )

    with patch(
        "data_module.phase3c_backfill_runner.fetch_institutional_flows",
        return_value=frame,
    ):
        summary = runner.run_backfill(
            date(2024, 7, 22),
            date(2024, 7, 22),
            dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )

    result = summary.daily_results[0]
    assert result["status"] == "SUCCESS"
    assert result["reconciliation"]["matched_row_count"] == 2
    assert result["reconciliation"]["missing_key_count"] == 0
    assert result["reconciliation"]["inserted_row_count"] == 1
    assert summary.total_rows_inserted == 1
    with sqlite3.connect(candidate_db) as conn:
        rows = conn.execute(
            "SELECT stock_code, foreign_investor_net FROM institutional_flows "
            "WHERE decision_date = '2024-07-22' ORDER BY stock_code"
        ).fetchall()
    assert rows == [("2317", 50), ("2330", 50)]


def test_runner_preserves_conflict_diagnostic_and_original_row(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    candidate_db = tmp_path / "candidate.db"
    incoming = _institutional_frame()
    existing = incoming.copy()
    existing.loc[0, "source_version"] = "conflicting-source"
    runner = Phase3CBackfillRunner(
        candidate_db,
        sources=("institutional",),
        production_data_root=prod_root,
        production_db_path=prod_db,
        rate_limit_seconds=0,
    )
    _seed_source_rows(runner, candidate_db, "institutional", existing)

    with patch(
        "data_module.phase3c_backfill_runner.fetch_institutional_flows",
        return_value=incoming,
    ):
        summary = runner.run_backfill(
            date(2024, 7, 22),
            date(2024, 7, 22),
            dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )

    result = summary.daily_results[0]
    assert result["status"] == "FAILED_RETRYABLE"
    assert "reconciliation_conflict" in result["error_message"]
    assert "source_version" in result["error_message"]
    assert result["reconciliation"]["status"] == "CONFLICT"
    assert result["reconciliation"]["conflict_key_count"] == 1
    with sqlite3.connect(candidate_db) as conn:
        source_version = conn.execute(
            "SELECT source_version FROM institutional_flows "
            "WHERE stock_code = '2330' AND decision_date = '2024-07-22'"
        ).fetchone()[0]
        checkpoint = conn.execute(
            "SELECT status, error_message FROM phase3c_backfill_checkpoints "
            "WHERE decision_date = '2024-07-22' AND source = 'institutional'"
        ).fetchone()
    assert source_version == "conflicting-source"
    assert checkpoint[0] == "FAILED_RETRYABLE"
    assert "reconciliation_conflict" in checkpoint[1]


def test_runner_rolls_back_partial_insert_when_candidate_write_fails(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    candidate_db = tmp_path / "candidate.db"
    frame = _institutional_frame_two_rows()
    runner = Phase3CBackfillRunner(
        candidate_db,
        sources=("institutional",),
        production_data_root=prod_root,
        production_db_path=prod_db,
        rate_limit_seconds=0,
    )
    with sqlite3.connect(candidate_db) as conn:
        runner._ensure_candidate_tables(conn)
        conn.execute(
            """
            CREATE TRIGGER reject_fixture_second_row
            BEFORE INSERT ON institutional_flows
            WHEN NEW.stock_code = '2317'
            BEGIN
                SELECT RAISE(ABORT, 'fixture insert failure');
            END;
            """
        )

    with patch(
        "data_module.phase3c_backfill_runner.fetch_institutional_flows",
        return_value=frame,
    ):
        summary = runner.run_backfill(
            date(2024, 7, 22),
            date(2024, 7, 22),
            dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )

    result = summary.daily_results[0]
    assert result["status"] == "FAILED_RETRYABLE"
    assert "reconciliation_write_failed" in result["error_message"]
    assert "fixture insert failure" in result["error_message"]
    with sqlite3.connect(candidate_db) as conn:
        row_count = conn.execute(
            "SELECT COUNT(*) FROM institutional_flows "
            "WHERE decision_date = '2024-07-22'"
        ).fetchone()[0]
        checkpoint = conn.execute(
            "SELECT status FROM phase3c_backfill_checkpoints "
            "WHERE decision_date = '2024-07-22' AND source = 'institutional'"
        ).fetchone()[0]
    assert row_count == 0
    assert checkpoint == "FAILED_RETRYABLE"


def test_runner_tdcc_default_preserves_historical_block(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    runner = Phase3CBackfillRunner(
        tmp_path / "candidate.db", sources=("tdcc",), production_data_root=prod_root,
        production_db_path=prod_db, rate_limit_seconds=0,
    )

    with patch("data_module.phase3c_backfill_runner.fetch_latest_tdcc_shareholding") as fetch:
        summary = runner.run_backfill(
            date(2024, 7, 22), date(2024, 7, 22), dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )

    fetch.assert_not_called()
    assert summary.daily_results[0]["status"] == "BLOCKED_NO_HISTORICAL_ENDPOINT"
    assert summary.succeeded_days_count == 0
    assert summary.skipped_days_count == 1


def test_runner_latest_tdcc_snapshot_uses_payload_date_and_checkpoint(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    cand_db = tmp_path / "candidate.db"
    runner = Phase3CBackfillRunner(
        cand_db, sources=("tdcc",), production_data_root=prod_root,
        production_db_path=prod_db, rate_limit_seconds=0,
        include_latest_tdcc_snapshot=True,
    )

    with patch(
        "data_module.phase3c_backfill_runner.fetch_latest_tdcc_shareholding",
        return_value=_tdcc_frame(),
    ) as fetch:
        summary = runner.run_backfill(
            date(2024, 7, 19), date(2024, 7, 22), dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )

    fetch.assert_called_once_with()
    assert len(summary.daily_results) == 1
    assert summary.daily_results[0]["decision_date"] == "2024-07-19"
    assert summary.daily_results[0]["status"] == "SUCCESS"
    assert summary.total_rows_inserted == 1
    assert "LATEST_SNAPSHOT_ENABLED" in summary.tdcc_historical_status
    with sqlite3.connect(cand_db) as conn:
        tdcc_rows = conn.execute(
            "SELECT stock_code, decision_date FROM tdcc_shareholding"
        ).fetchall()
        checkpoint = conn.execute(
            "SELECT decision_date, source, status, row_count "
            "FROM phase3c_backfill_checkpoints"
        ).fetchone()
    assert tdcc_rows == [("2330", "2024-07-19")]
    assert checkpoint == ("2024-07-19", "tdcc", "SUCCESS", 1)


def test_tdcc_rows_and_success_checkpoint_commit_atomically_and_retry_idempotently(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    candidate_db = tmp_path / "candidate.db"
    runner = Phase3CBackfillRunner(
        candidate_db,
        sources=("tdcc",),
        production_data_root=prod_root,
        production_db_path=prod_db,
        rate_limit_seconds=0,
        include_latest_tdcc_snapshot=True,
    )
    with sqlite3.connect(candidate_db) as conn:
        runner._ensure_candidate_tables(conn)
        conn.execute(
            """
            CREATE TRIGGER reject_tdcc_success_checkpoint
            BEFORE INSERT ON phase3c_backfill_checkpoints
            WHEN NEW.source = 'tdcc' AND NEW.status = 'SUCCESS'
            BEGIN
                SELECT RAISE(ABORT, 'fixture checkpoint failure');
            END;
            """
        )

    with patch(
        "data_module.phase3c_backfill_runner.fetch_latest_tdcc_shareholding",
        return_value=_tdcc_frame(),
    ) as fetch:
        failed = runner.run_backfill(
            date(2024, 7, 19), date(2024, 7, 22), dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )
        assert failed.daily_results[0]["status"] == "FAILED_RETRYABLE"
        with sqlite3.connect(candidate_db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM tdcc_shareholding").fetchone()[0] == 0
            checkpoint = conn.execute(
                "SELECT status FROM phase3c_backfill_checkpoints "
                "WHERE source='tdcc' AND decision_date='2024-07-19'"
            ).fetchone()
            assert checkpoint == ("FAILED_RETRYABLE",)
            conn.execute("DROP TRIGGER reject_tdcc_success_checkpoint")

        recovered = runner.run_backfill(
            date(2024, 7, 19), date(2024, 7, 22), dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )
        repeated = runner.run_backfill(
            date(2024, 7, 19), date(2024, 7, 22), dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
        )

    assert fetch.call_count == 3
    assert recovered.daily_results[0]["status"] == "SUCCESS"
    assert recovered.total_rows_inserted == 1
    assert repeated.daily_results[0]["status"] == "SKIPPED_ALREADY_EXISTS"
    with sqlite3.connect(candidate_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM tdcc_shareholding").fetchone()[0] == 1
        checkpoint = conn.execute(
            "SELECT status, row_count FROM phase3c_backfill_checkpoints "
            "WHERE source='tdcc' AND decision_date='2024-07-19'"
        ).fetchone()
    assert checkpoint == ("SUCCESS", 1)


def test_runner_cancellation_after_complete_fetch_preserves_result_and_reports_cancelled(tmp_path):
    prod_root, prod_db = _production_db(tmp_path)
    cancellation = {"requested": False}
    runner = Phase3CBackfillRunner(
        tmp_path / "candidate.db",
        sources=("institutional",),
        production_data_root=prod_root,
        production_db_path=prod_db,
        rate_limit_seconds=0,
        calendar=SimpleNamespace(
            get_trading_days_in_range=lambda start, end, *, allow_online_probe: [{
                "date": start,
                "date_str": start.isoformat(),
                "is_trading_day": True,
                "reason_code": "verified fixture session",
            }]
        ),
    )

    def _fetch(_day):
        cancellation["requested"] = True
        return _institutional_frame()

    with patch("data_module.phase3c_backfill_runner.fetch_institutional_flows", side_effect=_fetch):
        summary = runner.run_backfill(
            date(2024, 7, 22), date(2024, 7, 22), dry_run=False,
            confirm_token=APPLY_CONFIRM_TOKEN,
            cancel_callback=lambda: cancellation["requested"],
        )

    assert summary.cancelled is True
    assert summary.succeeded_days_count == 1
    assert summary.daily_results[0]["status"] == "SUCCESS"
    assert summary.daily_results[0]["row_count"] == 1
    with sqlite3.connect(tmp_path / "candidate.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM institutional_flows").fetchone()[0] == 1
