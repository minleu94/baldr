from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from ml_module.recommendation_calibration_authority import RecommendationPromotionPolicy
from ml_module.recommendation_calibration_evidence import RecommendationPredictionCaptureService
from scripts.scheduled import run_recommendation_natural_outcomes as natural_cli
from tests.natural_session_source_fixture import (
    VerifiedNaturalFixture,
    make_verified_natural_fixture,
)
from tests.test_daily_recommendation_learning_loop import (
    FEATURE_REGISTRY_HASH,
    FEATURE_SCHEMA,
    _candidate,
)


TAIPEI = ZoneInfo("Asia/Taipei")
CAPTURE_DAY = date(2026, 6, 1)
EVALUATION_DAY = "2026-07-27"


def _write_capture(tmp_path: Path) -> tuple[Path, VerifiedNaturalFixture]:
    _result, candidate_root, _metadata = _candidate(
        tmp_path,
        shift=0,
        candidate_day=CAPTURE_DAY.isoformat(),
    )
    fixture = make_verified_natural_fixture(
        tmp_path,
        (CAPTURE_DAY,),
        EVALUATION_DAY,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
    )
    capture_input = fixture.input_for(CAPTURE_DAY)
    endpoint_day = fixture.endpoint_dates[CAPTURE_DAY.isoformat()]
    with sqlite3.connect(fixture.db_path) as connection:
        # 這個 CLI fixture 要走真實 MLHistoricalSnapshotProvider；market-only
        # fixture 不足以讓 provider 驗證四張來源表，因此只在隔離 DB 補最小
        # schema 與 capture/endpoint 兩筆個股收盤價。
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS daily_prices (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                成交股數 INTEGER,
                成交金額 INTEGER,
                開盤價 TEXT,
                最高價 TEXT,
                最低價 TEXT,
                收盤價 TEXT
            );
            CREATE TABLE IF NOT EXISTS technical_indicators (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                RSI TEXT,
                MACD TEXT,
                ADX TEXT
            );
            CREATE TABLE IF NOT EXISTS industry_indices (
                日期 TEXT NOT NULL,
                指數名稱 TEXT,
                收盤指數 TEXT
            );
            """
        )
        symbol = capture_input.symbol
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (CAPTURE_DAY.strftime("%Y%m%d"), symbol, 100_000, 10_000_000, "100", "100", "100", "100"),
                (endpoint_day.replace("-", ""), symbol, 100_000, 12_000_000, "120", "120", "120", "120"),
            ),
        )
    capture = RecommendationPredictionCaptureService().capture(
        candidate_root=candidate_root,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        policy_hash=RecommendationPromotionPolicy().policy_hash,
        decision_date=CAPTURE_DAY.isoformat(),
        captured_at=f"{CAPTURE_DAY.isoformat()}T09:00:00+00:00",
        inputs=(capture_input,),
        fixed_round_trip_cost_bp=50,
        data_root=tmp_path / "formal-data",
        source_contract_binding=fixture.binding_for(CAPTURE_DAY),
    )
    capture_path = tmp_path / "capture.json"
    capture.persist(capture_path)
    return capture_path, fixture


def _run_cli(
    monkeypatch,
    capsys,
    *,
    capture_path: Path,
    fixture: VerifiedNaturalFixture,
    tmp_path: Path,
    evaluation_date: str | None = EVALUATION_DAY,
    calendar_cache_path: Path | None = None,
) -> dict[str, object]:
    checked_clock = fixture.evaluation_at.astimezone(TAIPEI)
    monkeypatch.setattr(natural_cli, "_taipei_now", lambda: checked_clock)
    output_path = tmp_path / "natural-evidence.json"
    args = [
        "--source-db",
        str(fixture.db_path),
        "--data-root",
        str(tmp_path / "data-root"),
        "--output-root",
        str(tmp_path / "output-root"),
        "--calendar-cache-path",
        str(calendar_cache_path or fixture.calendar_root),
        "--capture",
        str(capture_path),
        "--output",
        str(output_path),
    ]
    if evaluation_date is not None:
        args.extend(("--evaluation-date", evaluation_date))
    exit_code = natural_cli.main(args)
    assert exit_code == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines
    return json.loads(lines[-1])


def test_standalone_cli_injects_strict_resolver_and_source(tmp_path, monkeypatch, capsys) -> None:
    capture_path, fixture = _write_capture(tmp_path)

    result = _run_cli(
        monkeypatch,
        capsys,
        capture_path=capture_path,
        fixture=fixture,
        tmp_path=tmp_path,
        evaluation_date=None,
    )

    assert result["status"] == "matured"
    assert result["matured_sample_count"] == 1
    assert Path(str(result["evidence"]["receipt_path"])).is_file()


def test_standalone_cli_missing_calendar_stays_pending(tmp_path, monkeypatch, capsys) -> None:
    capture_path, fixture = _write_capture(tmp_path)

    result = _run_cli(
        monkeypatch,
        capsys,
        capture_path=capture_path,
        fixture=fixture,
        tmp_path=tmp_path,
        calendar_cache_path=tmp_path / "missing-calendar-cache",
    )

    assert result["status"] == "pending"
    assert result["matured_sample_count"] == 0
    assert any("calendar" in str(item) for item in result["diagnostics"])


def test_standalone_cli_historical_evaluation_date_stays_pending(tmp_path, monkeypatch, capsys) -> None:
    capture_path, fixture = _write_capture(tmp_path)

    result = _run_cli(
        monkeypatch,
        capsys,
        capture_path=capture_path,
        fixture=fixture,
        tmp_path=tmp_path,
        evaluation_date="2026-07-26",
    )

    assert result["status"] == "pending"
    assert result["matured_sample_count"] == 0
    assert "natural_maturity_evaluation_clock_mismatch" in result["diagnostics"]
