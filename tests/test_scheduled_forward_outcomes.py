from __future__ import annotations

from datetime import datetime
import json
import sqlite3
from pathlib import Path

from app_module.evidence_event_dtos import EvidenceDataQuality, EvidenceEventType
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.evidence_event_service import EvidenceEventService
from app_module.scheduled_forward_outcome_service import (
    run_scheduled_forward_outcomes,
)
from data_module.config import TWStockConfig


def _config(tmp_path: Path) -> TWStockConfig:
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")
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
        for index in range(7):
            day = f"202609{index + 1:02d}"
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


def test_dry_run_is_read_only_and_persists_receipt(tmp_path: Path) -> None:
    config = _config(tmp_path)
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
    assert result["summary"]["outcomes_created"] == 1
    assert result["summary"]["outcomes_written"] == 1
    assert EvidenceEventRepository(config).list_outcomes() == []
    status_path = Path(result["status_path"])
    run_path = Path(result["run_path"])
    assert status_path.is_file()
    assert run_path.is_file()
    assert json.loads(status_path.read_text(encoding="utf-8"))["status"] == "dry_run"


def test_identity_gate_skips_unbound_events_before_writing(tmp_path: Path) -> None:
    config = _config(tmp_path)
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


def test_legacy_identity_backlog_does_not_block_new_complete_cohort(tmp_path: Path) -> None:
    config = _config(tmp_path)
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
) -> None:
    config = _config(tmp_path)
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


def test_external_source_health_blocks_confirmed_run(tmp_path: Path) -> None:
    config = _config(tmp_path)

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


def test_confirmed_run_writes_only_outcomes(tmp_path: Path) -> None:
    config = _config(tmp_path)
    before_event_count = len(EvidenceEventRepository(config).list_events())
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

    assert result["status"] in {"passed", "passed_with_warnings"}
    assert result["writes_evidence_db"] is True
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
