from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.paper_portfolio_time import TAIWAN_MARKET_TIMEZONE
from app_module.recommendation_repository import RecommendationRepository
from data_module.config import TWStockConfig
from scripts.smoke_evidence_pipeline import build_parser, run_smoke
from tests.forward_outcome_test_support import write_verified_test_calendar_cache


ROOT = Path(__file__).resolve().parents[1]


def _config(tmp_path: Path) -> TWStockConfig:
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")
    config.db_file = tmp_path / "data" / "sqlite" / "twstock.db"
    config.db_file.parent.mkdir(parents=True, exist_ok=True)
    return config


def _seed_market_db(
    config: TWStockConfig,
    *,
    days: int = 8,
    with_benchmark: bool = True,
    start_date: str = "20260701",
) -> None:
    start_day = datetime.strptime(start_date, "%Y%m%d").date()
    with sqlite3.connect(config.db_file) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS daily_prices (
                日期 TEXT,
                證券代號 TEXT,
                收盤價 REAL,
                PRIMARY KEY (證券代號, 日期)
            );
            CREATE TABLE IF NOT EXISTS market_indices (
                日期 TEXT,
                指數名稱 TEXT,
                收盤指數 REAL,
                PRIMARY KEY (指數名稱, 日期)
            );
            CREATE TABLE IF NOT EXISTS industry_indices (
                日期 TEXT,
                指數名稱 TEXT,
                收盤指數 REAL,
                PRIMARY KEY (指數名稱, 日期)
            );
            """
        )
        for offset in range(days):
            day = (start_day + timedelta(days=offset)).strftime("%Y%m%d")
            conn.execute("INSERT OR REPLACE INTO daily_prices VALUES (?, ?, ?)", (day, "2330", 100 + offset))
            if with_benchmark:
                conn.execute("INSERT OR REPLACE INTO market_indices VALUES (?, ?, ?)", (day, "TAIEX", 10000 + offset))
            conn.execute("INSERT OR REPLACE INTO industry_indices VALUES (?, ?, ?)", (day, "半導體", 1000 + offset))


def _seed_recommendation(
    config: TWStockConfig,
    result_id: str = "rec-smoke-001",
    *,
    created_at: str = "2026-07-01T16:00:00",
) -> str:
    result = RecommendationResultDTO(
        result_id=result_id,
        result_name="Evidence Pipeline Smoke Fixture",
        config={"profile_id": "balanced", "profile_version": "1.0"},
        recommendations=[
            RecommendationDTO(
                stock_code="2330",
                stock_name="台積電",
                close_price=100.0,
                price_change=1.0,
                total_score=90.0,
                indicator_score=30.0,
                pattern_score=30.0,
                volume_score=30.0,
                recommendation_reasons="rank_top",
                industry="半導體",
                regime_match=True,
                score_percentile_bp=9500,
            )
        ],
        regime="Trend",
        created_at=created_at,
    )
    RecommendationRepository(config).save_result(result)
    return result.result_id


def _run_smoke(config: TWStockConfig, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "smoke_evidence_pipeline.py"),
            "--db-path",
            str(config.db_file),
            "--data-root",
            str(config.data_root),
            "--output-root",
            str(config.output_root),
            *args,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_confirm(
    config: TWStockConfig,
    invocation_at: datetime,
    *args: str,
) -> dict[str, object]:
    parsed = build_parser().parse_args(
        [
            "--db-path",
            str(config.db_file),
            "--data-root",
            str(config.data_root),
            "--output-root",
            str(config.output_root),
            *args,
        ]
    )
    calendar_cache = write_verified_test_calendar_cache(
        config.output_root / f"isolated_official_calendar_{uuid4().hex}",
        observed_at=invocation_at.astimezone(timezone.utc),
        year=invocation_at.year,
    )
    return run_smoke(
        parsed,
        _calendar_cache_path=calendar_cache,
        _now_provider=lambda: invocation_at,
    )


def test_evidence_pipeline_smoke_dry_run_does_not_write_events_or_outcomes(tmp_path):
    config = _config(tmp_path)
    _seed_market_db(config)
    result_id = _seed_recommendation(config)

    result = _run_smoke(
        config,
        "--recommendation-result-id",
        result_id,
        "--decision-date",
        "2026-07-01",
        "--windows",
        "5",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["events_seen"] == 1
    assert payload["events_inserted"] == 0
    assert payload["outcomes_created"] == 0
    assert EvidenceEventRepository(config).list_events() == []
    with sqlite3.connect(config.db_file.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        evidence_tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?)",
            ("evidence_events", "evidence_outcomes"),
        ).fetchall()
    assert evidence_tables == []


def test_evidence_pipeline_smoke_confirm_writes_event_and_ready_outcome(tmp_path):
    config = _config(tmp_path)
    _seed_market_db(config, days=12)
    result_id = _seed_recommendation(config)

    payload = _run_confirm(
        config,
        datetime(2026, 7, 20, 16, 0, tzinfo=TAIWAN_MARKET_TIMEZONE),
        "--recommendation-result-id",
        result_id,
        "--decision-date",
        "2026-07-01",
        "--windows",
        "5",
        "--confirm",
    )

    assert payload["dry_run"] is False
    assert payload["events_inserted"] == 1
    assert payload["outcomes_created"] == 1
    assert payload["outcome_status_counts"] == {"ready": 1}
    assert payload["sample_events"][0]["event_type"] == "recommendation_included"
    assert payload["sample_outcomes"][0]["return_basis"] == "close_to_close_event_date"


def test_evidence_pipeline_smoke_confirm_is_idempotent_for_duplicate_event(tmp_path):
    config = _config(tmp_path)
    _seed_market_db(config, days=12)
    result_id = _seed_recommendation(config)
    args = (
        "--recommendation-result-id",
        result_id,
        "--decision-date",
        "2026-07-01",
        "--windows",
        "5",
        "--confirm",
    )

    invocation_at = datetime(2026, 7, 20, 16, 0, tzinfo=TAIWAN_MARKET_TIMEZONE)
    first = _run_confirm(config, invocation_at, *args)
    second = _run_confirm(config, invocation_at, *args)

    payload = second
    assert payload["events_inserted"] == 0
    assert payload["events_skipped_duplicate"] == 1
    assert len(EvidenceEventRepository(config).list_events()) == 1


def test_evidence_pipeline_smoke_marks_future_data_insufficient_as_pending(tmp_path):
    config = _config(tmp_path)
    event_date = "2026-07-10"
    _seed_market_db(config, days=1, start_date="20260710")
    result_id = _seed_recommendation(
        config,
        created_at=f"{event_date}T16:00:00",
    )

    payload = _run_confirm(
        config,
        datetime(2026, 7, 10, 16, 0, tzinfo=TAIWAN_MARKET_TIMEZONE),
        "--recommendation-result-id",
        result_id,
        "--decision-date",
        event_date,
        "--windows",
        "5",
        "--confirm",
    )

    assert payload["outcomes_pending"] == 1
    assert payload["outcome_status_counts"] == {"insufficient_future_data": 1}


def test_evidence_pipeline_smoke_refuses_configured_canonical_database(tmp_path):
    canonical_root = tmp_path / "canonical-data"
    isolated_root = tmp_path / "isolated-data"
    env = dict(os.environ)
    env["DATA_ROOT"] = str(canonical_root)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "smoke_evidence_pipeline.py"),
            "--db-path",
            str(canonical_root / "sqlite" / "twstock.db"),
            "--data-root",
            str(isolated_root),
            "--output-root",
            str(tmp_path / "output"),
            "--recommendation-result-id",
            "rec-smoke-canonical-denied",
            "--decision-date",
            "2026-07-01",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "refuses the configured canonical database" in result.stderr
    assert not (canonical_root / "sqlite" / "twstock.db").exists()


def test_evidence_pipeline_smoke_missing_benchmark_does_not_stop_outcome(tmp_path):
    config = _config(tmp_path)
    _seed_market_db(config, days=12, with_benchmark=False)
    result_id = _seed_recommendation(config)

    payload = _run_confirm(
        config,
        datetime(2026, 7, 20, 16, 0, tzinfo=TAIWAN_MARKET_TIMEZONE),
        "--recommendation-result-id",
        result_id,
        "--decision-date",
        "2026-07-01",
        "--windows",
        "5",
        "--confirm",
    )

    assert payload["outcomes_created"] == 1
    assert payload["missing_benchmark"] == 1
    assert payload["outcome_status_counts"] == {"ready": 1}


def test_evidence_pipeline_smoke_summary_has_no_trading_language_and_no_ui_import():
    script_text = (ROOT / "scripts" / "smoke_evidence_pipeline.py").read_text(encoding="utf-8")

    assert "ui_qt" not in script_text
    lowered = script_text.lower()
    assert "target price" not in lowered
    assert "fair price" not in lowered
    assert "high confidence" not in lowered

