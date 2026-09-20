from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
from data_module.natural_maturity_session_resolver import NaturalMaturitySessionResolver
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)
from ml_module.recommendation_calibration_evidence import (
    verify_natural_maturity_session_proof,
)
from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario
from ml_module.recommendation_natural_outcome_service import (
    RecommendationNaturalOutcomeService,
)


CAPTURE_DATE = "2026-01-02"
EVALUATION_AT = datetime(2026, 2, 2, 8, 0, tzinfo=timezone.utc)
ENDPOINT_DATE = "2026-01-30"


def _write_calendar(root: Path, year: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(
        [
            {
                "Name": "國曆新年休市",
                "Date": f"{year - 1911:03d}0101",
                "Weekday": "四" if year == 2026 else "三",
                "Description": "測試用官方年度休市紀錄。",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    captured_at = datetime(2026, 1, 25, 8, 0, tzinfo=timezone.utc)
    cache = build_twse_calendar_cache(
        calendar_year=year,
        raw_response=raw,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
        response_headers={"ETag": f'"session-{year}"'},
        max_age=timedelta(days=31),
    )
    write_twse_calendar_cache(
        root / f"twse_holiday_schedule_{year}_test.json",
        cache,
        allowed_root=root,
    )


def _write_market_database(path: Path, *, include_endpoint_stock: bool) -> None:
    session_dates = (
        "20260105", "20260106", "20260107", "20260108", "20260109",
        "20260112", "20260113", "20260114", "20260115", "20260116",
        "20260119", "20260120", "20260121", "20260122", "20260123",
        "20260126", "20260127", "20260128", "20260129", "20260130",
    )
    with sqlite3.connect(path) as connection:
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
                指數名稱 TEXT,
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
        market_dates = ("20260102", *session_dates)
        for index, day in enumerate(market_dates, start=1):
            close = str(20_000 + index)
            connection.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?, ?)",
                (day, "TAIEX", close, close),
            )
        stock_rows = [("20260102", "2330", "100"),]
        if include_endpoint_stock:
            # 中間日期故意沒有個股列，endpoint 仍只按官方 session 精確取值。
            stock_rows.append((ENDPOINT_DATE.replace("-", ""), "2330", "120"))
        for day, symbol, close in stock_rows:
            connection.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (day, symbol, 100_000, 10_000_000, close, close, close, close),
            )


def _service_fixture(tmp_path: Path, *, include_endpoint_stock: bool) -> tuple[
    RecommendationNaturalOutcomeService,
    dict[str, object],
    NaturalMaturitySessionResolver,
]:
    database = tmp_path / "twstock.db"
    _write_market_database(database, include_endpoint_stock=include_endpoint_stock)
    calendar_root = tmp_path / "calendar"
    _write_calendar(calendar_root, 2025)
    _write_calendar(calendar_root, 2026)
    resolver = NaturalMaturitySessionResolver(database, calendar_root)
    scenario = build_legacy_cost_scenario(50)
    payload: dict[str, object] = {
        "capture_as_of_date": CAPTURE_DATE,
        "fixed_round_trip_cost_bp": 50,
        "rows": [{"row_id": "row-2330", "symbol": "2330"}],
        **scenario.metadata(),
    }
    service = RecommendationNaturalOutcomeService(
        MLHistoricalSnapshotProvider(database),
        session_resolver=resolver,
        evaluation_at=EVALUATION_AT,
    )
    return service, payload, resolver


def test_natural_outcome_uses_exact_twenty_official_sessions_and_verified_market(
    tmp_path: Path,
) -> None:
    service, payload, resolver = _service_fixture(
        tmp_path,
        include_endpoint_stock=True,
    )

    resolution = resolver.resolve(CAPTURE_DATE, EVALUATION_AT, horizon_sessions=20)
    assert resolution.status == "ready"
    assert resolution.endpoint_date == ENDPOINT_DATE
    assert resolution.proof is not None
    verified = verify_natural_maturity_session_proof(
        resolution.proof,
        capture_date=CAPTURE_DATE,
        label_end_date=ENDPOINT_DATE,
        evaluation_at=EVALUATION_AT,
        expected_db_path=tmp_path / "twstock.db",
    )
    outcomes, pending, diagnostics = service._outcomes_for_capture(
        payload,
        evaluation_day=EVALUATION_AT.astimezone(timezone(timedelta(hours=8))).date(),
        max_rows=10,
    )

    assert pending == 0
    assert diagnostics == ("liquidity_cost_missing:2330:2026-01-02",)
    assert len(outcomes) == 1
    assert outcomes[0].label_end_date == ENDPOINT_DATE
    assert outcomes[0].session_proof == verified


def test_natural_outcome_keeps_missing_endpoint_stock_pending(
    tmp_path: Path,
) -> None:
    service, payload, _resolver = _service_fixture(
        tmp_path,
        include_endpoint_stock=False,
    )

    outcomes, pending, diagnostics = service._outcomes_for_capture(
        payload,
        evaluation_day=EVALUATION_AT.astimezone(timezone(timedelta(hours=8))).date(),
        max_rows=10,
    )

    assert outcomes == []
    assert pending == 1
    assert diagnostics == (
        f"natural_maturity_endpoint_stock_close_invalid:2330:{ENDPOINT_DATE}",
    )


def test_natural_outcome_clock_mismatch_stays_pending(
    tmp_path: Path,
) -> None:
    service, payload, _resolver = _service_fixture(
        tmp_path,
        include_endpoint_stock=True,
    )

    outcomes, pending, diagnostics = service._outcomes_for_capture(
        payload,
        evaluation_day=EVALUATION_AT.astimezone(timezone(timedelta(hours=8))).date()
        + timedelta(days=1),
        max_rows=10,
    )

    assert outcomes == []
    assert pending == 1
    assert diagnostics == ("natural_maturity_evaluation_clock_mismatch",)
