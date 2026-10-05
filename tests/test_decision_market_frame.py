from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import pandas as pd

from app_module.decision_market_frame import DecisionMarketFrameLoader
from app_module.exceptions import BacktestCancelledError


def _seed_daily_prices(tmp_path: Path) -> Path:
    db_path = tmp_path / "market.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE daily_prices (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                收盤價 TEXT,
                漲跌價差 TEXT,
                成交股數 TEXT
            )
            """
        )
        start = date(2025, 11, 1)
        rows = []
        for offset in range(70):
            trade_date = start + timedelta(days=offset)
            for stock_code, price in (("2330", 100 + offset), ("2317", 80 + offset)):
                rows.append(
                    (
                        trade_date.strftime("%Y%m%d"),
                        stock_code,
                        str(price),
                        "1",
                        str(1000 + offset),
                    )
                )
        conn.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?)",
            rows,
        )
    return db_path


def test_loader_reuses_largest_frame_within_snapshot(tmp_path, monkeypatch) -> None:
    db_path = _seed_daily_prices(tmp_path)
    loader = DecisionMarketFrameLoader(db_path)
    calls = 0
    original = loader._read_frame

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(loader, "_read_frame", counted)
    target = date(2026, 1, 9)

    loader.reset(target)
    large = loader.load(target, 61)
    small = loader.load(target, 40)
    prices = loader.load_recent_prices("2330", target, 60)

    assert calls == 1
    assert large["日期"].nunique() == 61
    assert small["日期"].nunique() == 40
    assert len(prices) == 60
    assert prices[0][0] == target
    assert prices[0][1] == Decimal("169")

    loader.reset(target)
    loader.load(target, 61)
    assert calls == 2


def test_loader_reloads_when_larger_window_is_requested(tmp_path, monkeypatch) -> None:
    loader = DecisionMarketFrameLoader(_seed_daily_prices(tmp_path))
    target = date(2026, 1, 9)
    calls = 0
    original = loader._read_frame

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(loader, "_read_frame", counted)
    loader.reset(target)
    loader.load(target, 20)
    loader.load(target, 61)

    assert calls == 2


def test_loader_never_returns_rows_after_as_of_date(tmp_path) -> None:
    loader = DecisionMarketFrameLoader(_seed_daily_prices(tmp_path))
    target = date(2025, 12, 15)

    frame = loader.load(target, 61)

    normalized_dates = frame["日期"].astype(str).str.replace("-", "", regex=False)
    assert normalized_dates.max() <= target.strftime("%Y%m%d")


def test_recent_price_calls_reuse_one_grouped_market_window(
    tmp_path,
    monkeypatch,
) -> None:
    loader = DecisionMarketFrameLoader(_seed_daily_prices(tmp_path))
    target = date(2026, 1, 9)
    calls = 0
    original = loader._slice_to_lookback

    def counted(frame, lookback_days):
        nonlocal calls
        calls += 1
        return original(frame, lookback_days)

    monkeypatch.setattr(loader, "_slice_to_lookback", counted)
    loader.reset(target)
    first = loader.load_recent_prices("2330", target, 60)
    second = loader.load_recent_prices("2317", target, 60)
    repeated = loader.load_recent_prices("2330", target, 60)

    assert calls == 1
    assert first[0] == (target, Decimal("169"))
    assert second[0] == (target, Decimal("149"))
    assert repeated == first


def test_recent_price_batch_keeps_the_shared_market_date_window(tmp_path) -> None:
    db_path = _seed_daily_prices(tmp_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "DELETE FROM daily_prices WHERE 證券代號 = ? AND 日期 >= ?",
            ("2330", "20260108"),
        )

    loader = DecisionMarketFrameLoader(db_path)
    target = date(2026, 1, 9)
    prices = loader.load_recent_prices_batch(("2330", "2317"), target, 3)

    assert prices["2330"] == [(date(2026, 1, 7), Decimal("167"))]
    assert [day for day, _ in prices["2317"]] == [
        date(2026, 1, 9),
        date(2026, 1, 8),
        date(2026, 1, 7),
    ]


def test_recent_price_cache_tracks_source_identity_and_decision_date(tmp_path) -> None:
    db_path = _seed_daily_prices(tmp_path)
    loader = DecisionMarketFrameLoader(db_path)
    target = date(2026, 1, 9)

    assert loader.load_recent_prices("2330", target, 3)[0][1] == Decimal("169")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE daily_prices SET 收盤價 = ? WHERE 證券代號 = ? AND 日期 = ?",
            ("999", "2330", target.strftime("%Y%m%d")),
        )

    assert loader.load_recent_prices("2330", target, 3)[0][1] == Decimal("999")
    earlier = target - timedelta(days=1)
    earlier_prices = loader.load_recent_prices("2330", earlier, 3)

    assert earlier_prices[0][0] == earlier
    assert all(day <= earlier for day, _ in earlier_prices)


def test_sql_read_cancellation_propagates_and_allows_retry(tmp_path, monkeypatch) -> None:
    db_path = _seed_daily_prices(tmp_path)
    loader = DecisionMarketFrameLoader(db_path)
    loader.SQLITE_CANCEL_CHECK_INTERVAL = 1
    target = date(2026, 1, 9)
    cancel_state = {"enabled": True, "requested": False}
    original_read_sql_query = pd.read_sql_query

    def cancel_during_sql() -> bool:
        return cancel_state["requested"]

    def read_sql_query(sql, connection, *args, **kwargs):
        if cancel_state["enabled"] and "證券代號" in sql and "收盤價" in sql:
            connection.set_trace_callback(
                lambda statement: cancel_state.__setitem__("requested", True)
                if "證券代號" in statement and "收盤價" in statement
                else None
            )
        return original_read_sql_query(sql, connection, *args, **kwargs)

    monkeypatch.setattr("app_module.decision_market_frame.pd.read_sql_query", read_sql_query)

    with pytest.raises(BacktestCancelledError):
        loader.load_recent_prices("2330", target, 60, cancel_callback=cancel_during_sql)

    assert cancel_state["requested"]
    cancel_state["enabled"] = False
    assert loader.load_recent_prices("2330", target, 60)[0][0] == target


def test_non_cancelled_pandas_database_error_is_not_swallowed(tmp_path, monkeypatch) -> None:
    loader = DecisionMarketFrameLoader(_seed_daily_prices(tmp_path))

    def fail_read(*_args, **_kwargs):
        raise pd.errors.DatabaseError("查詢失敗")

    monkeypatch.setattr("app_module.decision_market_frame.pd.read_sql_query", fail_read)

    with pytest.raises(pd.errors.DatabaseError, match="查詢失敗"):
        loader.load_recent_prices("2330", date(2026, 1, 9), 60)


def test_cancel_request_does_not_mask_an_unrelated_database_failure(tmp_path, monkeypatch) -> None:
    loader = DecisionMarketFrameLoader(_seed_daily_prices(tmp_path))
    requested = False

    def fail_read(*_args, **_kwargs):
        nonlocal requested
        requested = True
        raise pd.errors.DatabaseError("真實查詢失敗")

    monkeypatch.setattr("app_module.decision_market_frame.pd.read_sql_query", fail_read)
    with pytest.raises(pd.errors.DatabaseError, match="真實查詢失敗"):
        loader.load_recent_prices(
            "2330", date(2026, 1, 9), 60, cancel_callback=lambda: requested
        )
