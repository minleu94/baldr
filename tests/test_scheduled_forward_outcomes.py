from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from app_module.evidence_event_dtos import EvidenceDataQuality, EvidenceEventType
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.evidence_event_service import EvidenceEventService
from app_module import scheduled_writer_reservation as writer_reservation
from app_module import scheduled_forward_outcome_service as forward_runner
from app_module.scheduled_writer_reservation import ScheduledWriterReservationWait
from app_module.forward_performance_service import ForwardOutcomeSummary
from app_module.evidence_event_dtos import EvidenceOutcome
from app_module.scheduled_forward_outcome_service import (
    run_scheduled_forward_outcomes,
)
from scripts.scheduled import run_scheduled_forward_outcomes as forward_cli
from data_module.config import TWStockConfig
from data_module.ml_storage_capacity import (
    acquire_heavy_chain_reservation,
    heavy_chain_lock_path,
    release_heavy_chain_reservation,
)
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)


def _install_verified_test_calendar(config: TWStockConfig, tmp_path: Path) -> None:
    cache_root = tmp_path / "official-calendar"
    cache_root.mkdir(parents=True, exist_ok=True)
    raw_response = json.dumps(
        [
            {
                "Name": "test-market-closure",
                "Date": "1150102",
                "Weekday": "星期五",
                "Description": "test fixture only",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    captured_times = (
        datetime.fromisoformat("2026-09-09T21:00:00+00:00"),
        datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    for index, captured_at in enumerate(captured_times):
        cache = build_twse_calendar_cache(
            calendar_year=2026,
            raw_response=raw_response,
            requested_at=captured_at - timedelta(seconds=1),
            captured_at=captured_at,
            response_status=200,
            response_headers={"ETag": f'"scheduled-outcome-test-{index}"'},
        )
        path = cache_root / f"twse_holiday_schedule_2026_test_{index}.json"
        write_twse_calendar_cache(path, cache, allowed_root=cache_root)
    config.official_calendar_cache_path = cache_root


def _config(tmp_path: Path) -> TWStockConfig:
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")
    _install_verified_test_calendar(config, tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.executescript(
            """
            CREATE TABLE daily_prices (
                日期 TEXT,
                證券代號 TEXT,
                收盤價 REAL,
                PRIMARY KEY (證券代號, 日期)
            );
            CREATE TABLE market_indices (
                日期 TEXT,
                指數名稱 TEXT,
                收盤指數 REAL,
                PRIMARY KEY (指數名稱, 日期)
            );
            CREATE TABLE industry_indices (
                日期 TEXT,
                指數名稱 TEXT,
                收盤指數 REAL,
                PRIMARY KEY (指數名稱, 日期)
            );
            """
        )
        price_days = (
            "20260901",
            "20260902",
            "20260903",
            "20260904",
            "20260907",
            "20260908",
            "20260909",
            "20260910",
        )
        for index, day in enumerate(price_days):
            conn.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?)",
                (day, "2330", 100 + index),
            )
            conn.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?)",
                (day, "TAIEX", 10_000 + index),
            )
            conn.execute(
                "INSERT INTO industry_indices VALUES (?, ?, ?)",
                (day, "半導體類指數", 2_000 + index),
            )
    EvidenceEventService(EvidenceEventRepository(config)).record_event(
        event_date="2026-09-01",
        decision_date="2026-09-01",
        symbol="2330",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
        event_family="recommendation",
        source_type="recommendation_result",
        source_id="scheduled-forward-test",
        reason_codes=("rank_top",),
        score_bp=7000,
        data_quality=EvidenceDataQuality.OBSERVED,
        as_of_date="2026-09-01",
        available_date="2026-09-01",
        source_version="test",
        strategy_version_id="strategy-v1",
        cost_model_id="cost-v1",
        benchmark_id="TAIEX",
        industry_benchmark_id="半導體類指數",
        metadata={"universe_id": "universe-v1", "horizon_days": 5},
    )
    return config


def _now() -> datetime:
    return datetime.fromisoformat("2026-09-10T06:00:00+08:00")


def _install_deterministic_writer_acquisition_clock(
    monkeypatch: pytest.MonkeyPatch,
    config: TWStockConfig,
    *,
    observed_waits: list[dict[str, Any]] | None = None,
) -> None:
    """Freeze service clocks while retaining a real isolated OS lease."""
    start = datetime(2026, 10, 4, 20, 0, tzinfo=timezone(timedelta(hours=8)))
    clock_calls = 0
    utc_clock_calls = 0
    original_wait = forward_runner.wait_for_scheduled_writer_reservation

    class DeterministicClock(datetime):
        @classmethod
        def now(cls, tz=None):
            nonlocal clock_calls
            current = start + timedelta(seconds=clock_calls * 10)
            clock_calls += 1
            return current.replace(tzinfo=None) if tz is None else current.astimezone(tz)

    monkeypatch.setattr(forward_runner, "datetime", DeterministicClock)

    def utc_now_for_test() -> datetime:
        nonlocal utc_clock_calls
        invocation_offset = max(0, clock_calls - 1) * 10
        current = start.astimezone(timezone.utc) + timedelta(
            seconds=invocation_offset + utc_clock_calls % 3
        )
        utc_clock_calls += 1
        return current

    monkeypatch.setattr(writer_reservation, "_utc_now", utc_now_for_test)

    def acquire_for_test(**kwargs: Any) -> ScheduledWriterReservationWait:
        if observed_waits is not None:
            observed_waits.append(dict(kwargs))
        assert Path(kwargs["release_root"]).resolve() == (
            config.output_root.resolve() / "release_v4"
        )
        return original_wait(**kwargs)

    monkeypatch.setattr(
        forward_runner,
        "wait_for_scheduled_writer_reservation",
        acquire_for_test,
    )


def test_dry_run_is_read_only_and_persists_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    observed_read_only: list[bool] = []
    original_repository = EvidenceEventRepository

    def build_read_only_repository(*args, **kwargs):
        repository = original_repository(*args, **kwargs)
        observed_read_only.append(repository.read_only)
        return repository

    def reject_schema_mutation(_repository) -> None:
        raise AssertionError("dry-run must not enter evidence schema mutation")

    monkeypatch.setattr(forward_runner, "EvidenceEventRepository", build_read_only_repository)
    monkeypatch.setattr(EvidenceEventRepository, "ensure_schema", reject_schema_mutation)
    result = run_scheduled_forward_outcomes(
        config=config,
        now=_now(),
        confirm=False,
        windows=(5,),
        start_date="2026-09-01",
        end_date="2026-09-10",
        data_as_of_date="2026-09-10",
    )

    assert result["status"] == "dry_run"
    assert result["writes_evidence_db"] is False
    assert result["source_db_changed"] is False
    assert observed_read_only == [True, True]
    assert result["summary"]["outcomes_created"] == 1
    assert result["summary"]["outcomes_written"] == 1
    assert result["summary"]["requested_data_as_of_date"] == "2026-09-10"
    assert result["summary"]["invocation_date_taipei"] == "2026-09-10"
    assert result["summary"]["price_read_cutoff_date"] == "2026-09-09"
    assert result["summary"]["price_read_cutoff_basis"] == (
        "current_session_close_not_reached"
    )
    assert EvidenceEventRepository(config).list_outcomes() == []
    status_path = Path(result["status_path"])
    run_path = Path(result["run_path"])
    assert status_path.is_file()
    assert run_path.is_file()
    assert json.loads(status_path.read_text(encoding="utf-8"))["status"] == "dry_run"


def test_default_calendar_context_never_falls_back_to_row_offset(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    missing_cache = tmp_path / "missing-official-calendar"
    config.official_calendar_cache_path = missing_cache
    result = run_scheduled_forward_outcomes(
        config=config,
        now=_now(),
        confirm=False,
        windows=(5,),
        start_date="2026-09-01",
        end_date="2026-09-10",
        data_as_of_date="2026-09-10",
    )

    assert result["maturity_calendar"]["status"] == "configured"
    assert result["maturity_calendar"]["cache_path"] == str(missing_cache.resolve())
    assert result["summary"]["blocked_time_contract_count"] == 1
    assert result["status"] == "dry_run"
    assert result["exit_code"] == 0
    assert result["health_classification"] == "actionable_engineering_blocker"
    assert result["health"]["blocked_time_contract_count"] == 1
    assert result["health"]["planned_official_maturity"]["time_contract_blocked_count"] == 1
    assert "official_maturity_calendar_unavailable" in result["health"]["blockers"]
    assert "official_maturity_calendar_unavailable" in result["blockers"]


def test_invalid_calendar_blocks_confirmed_run_with_named_health_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    _install_deterministic_writer_acquisition_clock(monkeypatch, config)
    invalid_cache = tmp_path / "invalid-official-calendar.json"
    invalid_cache.write_text("{}", encoding="utf-8")
    config.official_calendar_cache_path = invalid_cache

    result = run_scheduled_forward_outcomes(
        config=config,
        now=_now(),
        confirm=True,
        allow_production_db_confirm=True,
        windows=(5,),
        start_date="2026-09-01",
        end_date="2026-09-10",
        data_as_of_date="2026-09-10",
    )

    assert result["summary"]["blocked_time_contract_count"] == 1
    assert result["health"]["classification"] == "actionable_engineering_blocker"
    assert result["health_classification"] == "actionable_engineering_blocker"
    assert result["health"]["blocked_time_contract_count"] == 1
    assert result["health"]["planned_official_maturity"]["time_contract_blocked_count"] == 1
    assert "official_maturity_calendar_unavailable" in result["health"]["blockers"]
    assert result["status"] == "blocked"
    assert result["exit_code"] == 2
    assert "official_maturity_calendar_unavailable" in result["blockers"]
    outcomes = EvidenceEventRepository(config).list_outcomes()
    assert len(outcomes) == 1
    assert outcomes[0].metadata["time_contract_state"] == "blocked_time_contract"
    assert outcomes[0].metadata["readiness_blocker"] == "official_maturity_calendar_unavailable"


def test_cli_artifact_output_override_does_not_change_canonical_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canonical_output = tmp_path / "canonical-output"
    artifact_output = tmp_path / "shadow-output"
    configured: dict[str, object] = {}
    passed: dict[str, object] = {}
    config = type(
        "Config",
        (),
        {"output_root": canonical_output, "db_file": tmp_path / "canonical.db"},
    )()

    def build_config(**kwargs):
        configured.update(kwargs)
        return config

    def run_service(**kwargs):
        passed.update(kwargs)
        return {"status": "dry_run", "exit_code": 0}

    monkeypatch.setattr(forward_cli, "TWStockConfig", build_config)
    monkeypatch.setattr(forward_cli, "run_scheduled_forward_outcomes", run_service)

    exit_code = forward_cli.main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(artifact_output),
        ]
    )

    assert exit_code == 0
    assert configured == {"data_root": tmp_path / "data"}
    assert passed["config"] is config
    assert config.output_root == canonical_output
    assert passed["output_root"] == artifact_output
    assert capsys.readouterr().out.strip() == '{"exit_code": 0, "status": "dry_run"}'


def test_identity_gate_skips_unbound_events_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    _install_deterministic_writer_acquisition_clock(monkeypatch, config)
    EvidenceEventService(EvidenceEventRepository(config)).record_event(
        event_date="2026-09-02",
        decision_date="2026-09-02",
        symbol="2330",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
        event_family="recommendation",
        source_type="legacy_recommendation_result",
        source_id="unbound-event",
        reason_codes=("legacy",),
        score_bp=6000,
        data_quality=EvidenceDataQuality.OBSERVED,
        as_of_date="2026-09-02",
        available_date="2026-09-02",
        source_version="test",
    )

    result = run_scheduled_forward_outcomes(
        config=config,
        now=_now(),
        confirm=True,
        allow_production_db_confirm=True,
        windows=(5,),
        start_date="2026-09-01",
        end_date="2026-09-10",
        data_as_of_date="2026-09-10",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED.value,
        require_cohort_identity=True,
    )

    assert result["status"] == "blocked"
    assert result["exit_code"] == 2
    assert result["blockers"] == ["events_missing_complete_cohort_identity"]
    assert result["health_classification"] == "actionable_engineering_blocker"
    assert result["blocking_reason"] == "events_missing_complete_cohort_identity"
    assert "不回填既有事件" in result["next_action"]
    assert result["recovery_verification"]["status"] == "required"
    assert result["summary"]["events_scanned"] == 1
    assert result["summary"]["events_skipped_incomplete_identity"] == 1
    assert result["summary"]["outcomes_created"] == 1
    assert len(EvidenceEventRepository(config).list_outcomes()) == 1


def test_legacy_identity_backlog_does_not_block_new_complete_cohort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    _install_deterministic_writer_acquisition_clock(monkeypatch, config)
    event_service = EvidenceEventService(EvidenceEventRepository(config))
    event_service.record_event(
        event_date="2026-09-02",
        decision_date="2026-09-02",
        symbol="2330",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
        event_family="recommendation",
        source_type="legacy_recommendation_result",
        source_id="legacy-backlog-event",
        reason_codes=("legacy",),
        score_bp=6000,
        data_quality=EvidenceDataQuality.OBSERVED,
        as_of_date="2026-09-02",
        available_date="2026-09-02",
        source_version="test",
    )
    event_service.record_event(
        event_date="2026-09-03",
        decision_date="2026-09-03",
        symbol="2330",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
        event_family="recommendation",
        source_type="recommendation_result",
        source_id="new-v4-cohort-event",
        reason_codes=("rank_top",),
        score_bp=7000,
        data_quality=EvidenceDataQuality.OBSERVED,
        as_of_date="2026-09-03",
        available_date="2026-09-03",
        source_version="test",
        strategy_version_id="strategy-v2",
        cost_model_id="cost-v2",
        benchmark_id="TAIEX",
        industry_benchmark_id="半導體類指數",
        metadata={
            "strategy_config_id": "strategy-config-v2",
            "strategy_config_schema": "strategy-config.v1",
            "universe_policy_id": "policy-v2",
            "universe_policy_hash": "policy-hash-v2",
            "universe_snapshot_id": "snapshot-v2-20260903",
            "universe_snapshot_hash": "snapshot-hash-v2",
            "horizon_days": 5,
        },
    )

    result = run_scheduled_forward_outcomes(
        config=config,
        now=_now(),
        confirm=True,
        allow_production_db_confirm=True,
        windows=(5,),
        max_events=1,
        start_date="2026-09-02",
        end_date="2026-09-10",
        data_as_of_date="2026-09-10",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED.value,
        require_cohort_identity=True,
    )

    assert result["health_classification"] != "actionable_engineering_blocker"
    assert result["blockers"] == []
    assert result["summary"]["events_scanned"] == 1
    assert result["summary"]["events_skipped_incomplete_identity"] == 1
    assert "legacy_incomplete_identity_skipped_without_backfill" in result["health"]["warnings"]
    assert len(EvidenceEventRepository(config).list_outcomes()) == 1


def test_natural_maturity_remains_waiting_and_exposes_recovery_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    _install_deterministic_writer_acquisition_clock(monkeypatch, config)
    EvidenceEventService(EvidenceEventRepository(config)).record_event(
        event_date="2026-09-07",
        decision_date="2026-09-07",
        symbol="2330",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
        event_family="recommendation",
        source_type="recommendation_result",
        source_id="pending-event",
        reason_codes=("rank_top",),
        score_bp=7000,
        data_quality=EvidenceDataQuality.OBSERVED,
        as_of_date="2026-09-07",
        available_date="2026-09-07",
        source_version="test",
        strategy_version_id="strategy-v1",
        cost_model_id="cost-v1",
        benchmark_id="TAIEX",
        industry_benchmark_id="半導體類指數",
        metadata={"universe_id": "universe-v1", "horizon_days": 5},
    )

    result = run_scheduled_forward_outcomes(
        config=config,
        now=_now(),
        confirm=True,
        allow_production_db_confirm=True,
        windows=(5,),
        start_date="2026-09-01",
        end_date="2026-09-10",
        data_as_of_date="2026-09-10",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED.value,
        require_cohort_identity=True,
    )

    assert result["status"] == "passed_with_warnings"
    assert result["exit_code"] == 0
    assert result["blockers"] == []
    assert result["health_classification"] == "waiting_for_natural_maturity"
    assert result["blocking_reason"] is None
    assert "等待官方交易日" in result["next_action"] or "等待下一個官方交易日" in result["next_action"]
    assert result["recovery_verification"]["status"] == "wait_until_natural_maturity"
    assert result["recovery_verification"]["next_maturity_date"] == result["next_maturity_date"]
    assert result["summary"]["pending_insufficient_future_data"] > 0
    assert result["summary"]["blocked_time_contract_count"] == 0
    assert result["health"]["blocked_time_contract_count"] == 0


def test_external_source_health_blocks_confirmed_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    _install_deterministic_writer_acquisition_clock(monkeypatch, config)

    result = run_scheduled_forward_outcomes(
        config=config,
        now=_now(),
        confirm=True,
        allow_production_db_confirm=True,
        windows=(5,),
        start_date="2026-08-01",
        end_date="2026-08-02",
        data_as_of_date="2026-09-10",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED.value,
        require_cohort_identity=True,
    )

    assert result["status"] == "blocked"
    assert result["exit_code"] == 2
    assert result["health_classification"] == "external_source_missing"
    assert result["blocking_reason"] == "no_events_in_window"
    assert result["blockers"] == ["no_events_in_window"]
    assert result["recovery_verification"]["status"] == "required"
    assert result["summary"]["events_scanned"] == 0


def test_stale_calendar_receipt_is_not_used_for_weekday_progress(tmp_path: Path) -> None:
    config = _config(tmp_path)
    freshness_dir = config.output_root / "scheduled" / "data_freshness"
    freshness_dir.mkdir(parents=True)
    (freshness_dir / "latest_status.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "checked_at": "2026-09-09T05:00:00+08:00",
                "checks": {
                    "official_calendar": {
                        "freshness_status": "current",
                        "records": [
                            {
                                "date_str": "2026-09-10",
                                "is_trading_day": False,
                                "reason_code": "twse_holiday_schedule_closed",
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = run_scheduled_forward_outcomes(
        config=config,
        now=_now(),
        confirm=False,
        windows=(5,),
        start_date="2026-09-01",
        end_date="2026-09-10",
        data_as_of_date="2026-09-10",
        require_cohort_identity=True,
    )

    assert result["calendar_observation"]["is_trading_day"] is None
    assert result["calendar_observation"]["reason_code"] == "official_calendar_observation_stale"
    progress = json.loads(
        Path(result["progress_receipt_path"]).read_text(encoding="utf-8")
    )
    assert progress["daily"]["data_expected"] is True
    assert "official_calendar_observation_unknown" in progress["warnings"]


def test_production_confirm_requires_explicit_allowance(tmp_path: Path) -> None:
    config = _config(tmp_path)
    result = run_scheduled_forward_outcomes(
        config=config,
        now=_now(),
        confirm=True,
        windows=(5,),
        start_date="2026-09-01",
        end_date="2026-09-10",
        data_as_of_date="2026-09-10",
    )

    assert result["status"] == "blocked"
    assert result["blockers"] == ["production_db_confirmation_required"]
    assert EvidenceEventRepository(config).list_outcomes() == []


def test_confirmed_run_writes_only_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    shadow_output = tmp_path / "shadow-output"
    before_event_count = len(EvidenceEventRepository(config).list_events())
    original_upsert = EvidenceEventRepository.upsert_outcomes
    original_repository = forward_runner.EvidenceEventRepository
    observed_read_only: list[bool] = []

    def build_tracked_repository(*args, **kwargs):
        repository = original_repository(*args, **kwargs)
        observed_read_only.append(repository.read_only)
        return repository

    def verify_writer_holds_shared_lock(repository, outcomes):
        competing = acquire_heavy_chain_reservation(
            heavy_chain_lock_path(config.output_root / "release_v4")
        )
        assert competing is None
        return original_upsert(repository, outcomes)

    monkeypatch.setattr(EvidenceEventRepository, "upsert_outcomes", verify_writer_holds_shared_lock)
    monkeypatch.setattr(forward_runner, "EvidenceEventRepository", build_tracked_repository)
    wait_arguments: list[dict[str, Any]] = []
    _install_deterministic_writer_acquisition_clock(
        monkeypatch,
        config,
        observed_waits=wait_arguments,
    )
    result = run_scheduled_forward_outcomes(
        config=config,
        output_root=shadow_output,
        now=_now(),
        confirm=True,
        allow_production_db_confirm=True,
        windows=(5,),
        start_date="2026-09-01",
        end_date="2026-09-10",
        data_as_of_date="2026-09-10",
    )

    assert result["status"] in {"passed", "passed_with_warnings"}
    assert result["writes_evidence_db"] is True
    assert result["reservation_wait"]["status"] == "acquired"
    assert observed_read_only == [False, True]
    assert result["reservation_acquire_guard"]["passed"] is True
    assert result["canonical_reservation_root"] == str(config.output_root.resolve())
    assert result["artifact_output_root"] == str(shadow_output.resolve())
    assert Path(result["status_path"]).is_relative_to(shadow_output.resolve())
    assert Path(wait_arguments[0]["release_root"]).resolve() == config.output_root.resolve() / "release_v4"
    assert wait_arguments[0]["timeout_seconds"] == forward_runner.SCHEDULED_WRITER_RESERVATION_TIMEOUT_SECONDS
    invocation_date = datetime.fromisoformat(result["invocation_started_at"]).astimezone(
        forward_runner.TAIPEI
    ).date()
    assert wait_arguments[0]["latest_acquire_at"] == datetime.combine(
        invocation_date + timedelta(days=1),
        datetime.min.time(),
        tzinfo=forward_runner.TAIPEI,
    ) - timedelta(seconds=forward_runner.FORWARD_OUTCOME_COMPLETION_RESERVE_SECONDS)
    assert result["summary"]["outcomes_created"] == 1
    assert result["summary"]["outcomes_written"] == 1
    repository = EvidenceEventRepository(config)
    assert len(repository.list_events()) == before_event_count
    outcomes = repository.list_outcomes()
    assert len(outcomes) == 1
    assert outcomes[0].return_basis == "close_to_close_event_date"
    outcome_id = outcomes[0].outcome_id

    second = run_scheduled_forward_outcomes(
        config=config,
        output_root=shadow_output,
        now=_now(),
        confirm=True,
        allow_production_db_confirm=True,
        windows=(5,),
        start_date="2026-09-01",
        end_date="2026-09-10",
        data_as_of_date="2026-09-10",
    )
    assert second["summary"]["outcomes_created"] == 0
    assert second["summary"]["outcomes_updated"] == 1
    assert second["summary"]["outcomes_written"] == 1
    outcomes_after_retry = repository.list_outcomes()
    assert len(outcomes_after_retry) == 1
    assert outcomes_after_retry[0].outcome_id == outcome_id
    after_release = acquire_heavy_chain_reservation(
        heavy_chain_lock_path(config.output_root / "release_v4")
    )
    assert after_release is not None
    release_heavy_chain_reservation(after_release)


def test_reservation_timeout_blocks_before_confirmed_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    before = config.db_file.read_bytes()
    timeout_receipt = {
        "schema_version": "scheduled-writer-reservation-wait.v1",
        "status": "timed_out",
        "attempt_count": 3,
        "lock_path": str(heavy_chain_lock_path(config.output_root / "release_v4")),
    }
    monkeypatch.setattr(
        forward_runner,
        "wait_for_scheduled_writer_reservation",
        lambda **_kwargs: ScheduledWriterReservationWait(None, timeout_receipt),
    )
    monkeypatch.setattr(
        forward_runner,
        "EvidenceEventRepository",
        lambda *_args, **_kwargs: pytest.fail("writer repository opened after lock timeout"),
    )

    result = run_scheduled_forward_outcomes(
        config=config,
        now=_now(),
        confirm=True,
        allow_production_db_confirm=True,
        windows=(5,),
        start_date="2026-09-01",
        end_date="2026-09-10",
        data_as_of_date="2026-09-10",
    )

    assert result["status"] == "blocked"
    assert result["blockers"] == ["heavy_chain_reservation_timeout"]
    assert result["writes_evidence_db"] is False
    assert result["reservation_wait"] == timeout_receipt
    assert config.db_file.read_bytes() == before


def test_forward_acquire_guard_rejects_clock_jump_past_completion_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    before_bytes = config.db_file.read_bytes()
    before = datetime.fromisoformat("2026-10-04T10:00:00+08:00")
    after_cutoff = datetime.fromisoformat("2026-10-04T23:01:00+08:00")
    calls = 0

    class JumpClock(datetime):
        @classmethod
        def now(cls, tz=None):
            nonlocal calls
            if tz == forward_runner.TAIPEI:
                calls += 1
                return before if calls == 1 else after_cutoff
            return datetime.now(tz)

    def acquire_immediately(**kwargs):
        lease = acquire_heavy_chain_reservation(
            heavy_chain_lock_path(Path(kwargs["release_root"]))
        )
        assert lease is not None
        return ScheduledWriterReservationWait(
            lease,
            {"schema_version": "scheduled-writer-reservation-wait.v1", "status": "acquired"},
        )

    monkeypatch.setattr(forward_runner, "datetime", JumpClock)
    monkeypatch.setattr(forward_runner, "wait_for_scheduled_writer_reservation", acquire_immediately)
    original_release = forward_runner.release_heavy_chain_reservation

    def release_then_report_failure(reservation) -> None:
        original_release(reservation)
        raise OSError("simulated reservation release reporting failure")

    monkeypatch.setattr(forward_runner, "release_heavy_chain_reservation", release_then_report_failure)
    monkeypatch.setattr(
        forward_runner,
        "EvidenceEventRepository",
        lambda *_args, **_kwargs: pytest.fail("writer repository opened after cutoff guard failed"),
    )
    original_persist = forward_runner._persist_receipt

    def persist_only_after_reservation_release(payload, **kwargs):
        available = acquire_heavy_chain_reservation(
            heavy_chain_lock_path(config.output_root / "release_v4")
        )
        assert available is not None
        release_heavy_chain_reservation(available)
        return original_persist(payload, **kwargs)

    monkeypatch.setattr(forward_runner, "_persist_receipt", persist_only_after_reservation_release)

    result = run_scheduled_forward_outcomes(
        config=config,
        confirm=True,
        allow_production_db_confirm=True,
        windows=(5,),
    )

    assert result["status"] == "blocked"
    assert "heavy_chain_reservation_after_completion_cutoff" in result["blockers"]
    assert "heavy_chain_reservation_release_failed" in result["blockers"]
    assert "simulated reservation release reporting failure" in result["reservation_release_error"]
    assert result["reservation_acquire_guard"]["passed"] is False
    assert result["writes_evidence_db"] is False
    assert config.db_file.read_bytes() == before_bytes
    after_release = acquire_heavy_chain_reservation(
        heavy_chain_lock_path(config.output_root / "release_v4")
    )
    assert after_release is not None
    release_heavy_chain_reservation(after_release)


def test_natural_forward_clock_is_sampled_after_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    _install_deterministic_writer_acquisition_clock(monkeypatch, config)
    result = run_scheduled_forward_outcomes(
        config=config,
        confirm=True,
        allow_production_db_confirm=True,
        windows=(5,),
    )

    assert result["reservation_wait"]["status"] == "acquired"
    assert result["reservation_acquire_guard"]["passed"] is True
    checked_at = datetime.fromisoformat(result["checked_at"]).astimezone(timezone.utc)
    invocation_at = datetime.fromisoformat(result["invocation_started_at"]).astimezone(
        timezone.utc
    )
    wait_ended_at = datetime.fromisoformat(
        str(result["reservation_wait"]["wait_ended_at_utc"]).replace("Z", "+00:00")
    )
    assert checked_at > invocation_at
    assert checked_at >= wait_ended_at.replace(microsecond=0)


def test_health_reports_row_level_official_target_source_gaps(tmp_path: Path) -> None:
    config = _config(tmp_path)
    repository = EvidenceEventRepository(config)
    events = repository.list_events(start_date="2026-09-01", end_date="2026-09-10")
    assert len(events) == 1
    event = events[0]
    lookup_detail = {
        "status": "close_missing",
        "target_date": "2026-09-09",
        "row_count": 1,
        "close_value": None,
    }
    repository.upsert_outcome(
        EvidenceOutcome(
            outcome_id=f"{event.event_id}:5:close_to_close_event_date",
            event_id=event.event_id,
            window_days=5,
            outcome_status="missing_price",
            metadata={
                "maturity_basis": "official_market_sessions",
                "planned_official_maturity_date": "2026-09-09",
                "expected_maturity_date": "2026-09-08",
                "target_price_state": "missing_at_planned_official_session",
                "source_price_gap_reason": "no_close_on_planned_official_session",
                "official_target_price_lookup_detail": lookup_detail,
            },
        )
    )

    health = forward_runner._build_daily_health(
        config=config,
        db_path=config.db_file,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 10),
        event_type=None,
        symbol=None,
        limit=64,
        windows=(5,),
        checked_at=_now(),
        summary=ForwardOutcomeSummary(
            events_scanned=1,
            missing_outcome_price=1,
            dry_run=False,
        ),
        require_cohort_identity=False,
    )

    assert health["classification"] == "external_source_missing"
    assert health["blockers"] == ["outcome_price_missing"]
    assert health["outcome_source_gap_count"] == 1
    assert health["outcome_source_gaps"] == [
        {
            "event_id": event.event_id,
            "symbol": "2330",
            "window_days": 5,
            "outcome_status": "missing_price",
            "maturity_basis": "official_market_sessions",
            "planned_official_maturity_date": "2026-09-09",
            "expected_maturity_date": "2026-09-08",
            "target_price_state": "missing_at_planned_official_session",
            "source_price_gap_reason": "no_close_on_planned_official_session",
            "official_target_price_lookup_detail": lookup_detail,
        }
    ]
    repository.upsert_outcome(
        EvidenceOutcome(
            outcome_id=f"{event.event_id}:5:close_to_close_event_date",
            event_id=event.event_id,
            window_days=5,
            outcome_status="insufficient_future_data",
            metadata={
                "maturity_basis": "official_market_sessions",
                "planned_official_maturity_date": "2026-09-18",
                "expected_maturity_date": "2026-09-08",
                "target_price_state": "waiting_for_planned_official_session",
                "source_price_gap_reason": None,
            },
        )
    )
    waiting_health = forward_runner._build_daily_health(
        config=config,
        db_path=config.db_file,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 10),
        event_type=None,
        symbol=None,
        limit=64,
        windows=(5,),
        checked_at=_now(),
        summary=ForwardOutcomeSummary(
            events_scanned=1,
            pending_insufficient_future_data=1,
            dry_run=False,
        ),
        require_cohort_identity=False,
    )
    assert waiting_health["outcome_source_gap_count"] == 0
    assert waiting_health["outcome_source_gaps"] == []


def test_missing_required_source_table_blocks_before_calculation(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute("DROP TABLE daily_prices")
    result = run_scheduled_forward_outcomes(config=config, now=_now(), confirm=True)

    assert result["status"] == "blocked"
    assert "required_table_missing:daily_prices" in result["blockers"]
    assert "summary" not in result


def test_future_visible_date_is_rejected(tmp_path: Path) -> None:
    config = _config(tmp_path)
    result = run_scheduled_forward_outcomes(
        config=config,
        now=_now(),
        data_as_of_date="2026-09-11",
    )

    assert result["status"] == "blocked"
    assert result["blockers"][0].startswith("producer_error:ScheduledForwardOutcomeError:")
