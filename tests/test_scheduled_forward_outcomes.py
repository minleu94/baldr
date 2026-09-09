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
