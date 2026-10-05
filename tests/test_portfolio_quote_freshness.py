from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app_module.market_session_cadence import MarketSessionCadence
from app_module.portfolio_service import PortfolioService
from app_module.position_health_source_providers import OfficialCalendarSourceProvider
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)

TAIPEI = ZoneInfo("Asia/Taipei")


def _cadence(tmp_path: Path, now: datetime) -> MarketSessionCadence:
    captured = datetime(2026, 9, 28, tzinfo=timezone.utc)
    raw = json.dumps(
        [
            {"Name": "年度休市", "Date": "1150101", "Weekday": "四", "Description": "放假1日。"},
            {"Name": "國慶補假", "Date": "1151009", "Weekday": "五", "Description": "放假1日。"},
        ],
        ensure_ascii=False,
    ).encode("utf-8")
    cache = build_twse_calendar_cache(
        calendar_year=2026,
        raw_response=raw,
        requested_at=captured - timedelta(seconds=1),
        captured_at=captured,
        response_status=200,
        response_headers={"Content-Type": "application/json"},
        max_age=timedelta(days=31),
    )
    cache_dir = tmp_path / "calendar"
    cache_dir.mkdir(parents=True, exist_ok=True)
    write_twse_calendar_cache(
        cache_dir / "twse_holiday_schedule_2026.json",
        cache,
        allowed_root=tmp_path,
    )
    return MarketSessionCadence(
        OfficialCalendarSourceProvider(calendar_cache_path=cache_dir),
        clock=lambda: now,
    )


def _service(tmp_path: Path, now: datetime, *, use_sqlite: bool = False) -> PortfolioService:
    daily_price_dir = tmp_path / "daily_price"
    daily_price_dir.mkdir(parents=True, exist_ok=True)
    config = SimpleNamespace(
        output_root=tmp_path / "output",
        daily_price_dir=daily_price_dir,
        use_sqlite=use_sqlite,
        db_file=tmp_path / "twstock.db",
    )
    return PortfolioService(
        config,
        market_session_cadence=_cadence(tmp_path, now),
        now_provider=lambda: now,
    )


def test_csv_quote_observation_uses_actual_file_date_and_verified_weekend_session(tmp_path: Path):
    now = datetime(2026, 10, 4, 8, tzinfo=TAIPEI)
    service = _service(tmp_path, now)
    raw = "證券代號,收盤價\n2330,55.00\n".encode("utf-8")
    (service.config.daily_price_dir / "20261002.csv").write_bytes(raw)

    observation = service.get_current_price_observation("2330")

    assert observation.price == Decimal("55.00")
    assert observation.data_date == date(2026, 10, 2)
    assert observation.source_id == "csv.daily_prices"
    assert observation.source_snapshot_hash == sha256(raw).hexdigest()
    assert observation.freshness_status == "current"
    assert observation.expected_date == date(2026, 10, 2)


def test_csv_quote_observation_marks_prior_session_stale_after_next_session_close(tmp_path: Path):
    now = datetime(2026, 10, 5, 22, tzinfo=TAIPEI)
    service = _service(tmp_path, now)
    (service.config.daily_price_dir / "20261002.csv").write_text(
        "證券代號,收盤價\n2330,55.00\n", encoding="utf-8"
    )

    observation = service.get_current_price_observation("2330")

    assert observation.freshness_status == "stale"
    assert observation.data_date == date(2026, 10, 2)
    assert observation.expected_date == date(2026, 10, 5)


def test_quote_with_unparseable_file_date_is_observation_only(tmp_path: Path):
    now = datetime(2026, 10, 4, 8, tzinfo=TAIPEI)
    service = _service(tmp_path, now)
    (service.config.daily_price_dir / "latest.csv").write_text(
        "證券代號,收盤價\n2330,55.00\n", encoding="utf-8"
    )

    observation = service.get_current_price_observation("2330")

    assert observation.price is not None
    assert observation.data_date is None
    assert observation.freshness_status == "unverified"
    assert observation.expected_date is None


def test_empty_and_non_numeric_stock_codes_are_rejected_before_lookup(tmp_path: Path):
    service = _service(
        tmp_path,
        datetime(2026, 10, 4, 8, tzinfo=TAIPEI),
        use_sqlite=True,
    )

    missing = service.get_current_price_observation("   ")
    assert missing.stock_code == ""
    assert missing.freshness_reason == "stock_code_missing"

    for code in ("-", "--", "ABC", "2330A"):
        observation = service.get_current_price_observation(code)
        assert observation.stock_code == code
        assert observation.price is None
        assert observation.freshness_status == "unverified"
        assert observation.freshness_reason == "stock_code_invalid"


def test_non_numeric_quote_prices_are_unverified_without_decimal_exception(tmp_path: Path):
    now = datetime(2026, 10, 4, 8, tzinfo=TAIPEI)
    service = _service(tmp_path, now)
    csv_path = service.config.daily_price_dir / "20261002.csv"

    for raw_price in ("-", "--", "not-a-number"):
        csv_path.write_text(
            f"證券代號,收盤價\n2330,{raw_price}\n", encoding="utf-8"
        )
        observation = service.get_current_price_observation("2330")
        assert observation.price is None
        assert observation.freshness_status == "unverified"
        assert observation.freshness_reason == "quote_date_or_fingerprint_missing"


def test_sqlite_quote_observation_fingerprints_exact_row_and_keeps_read_only_path(tmp_path: Path):
    now = datetime(2026, 10, 4, 8, tzinfo=TAIPEI)
    service = _service(tmp_path, now, use_sqlite=True)
    db_path = service.config.db_file
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 開盤價 REAL, 最高價 REAL, "
            "最低價 REAL, 收盤價 REAL, 成交股數 INTEGER, 成交金額 INTEGER)"
        )
        connection.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("20261002", "2330", 54, 56, 53, 55, 1000, 55000),
        )
        connection.commit()
    before = db_path.stat().st_mtime_ns

    observation = service.get_current_price_observation("2330")

    assert observation.price == Decimal("55.0")
    assert observation.data_date == date(2026, 10, 2)
    assert observation.source_id == "sqlite.daily_prices"
    assert len(observation.source_snapshot_hash) == 64
    assert observation.freshness_status == "current"
    assert observation.expected_date == date(2026, 10, 2)
    assert db_path.stat().st_mtime_ns == before
