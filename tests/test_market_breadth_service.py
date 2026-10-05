from datetime import date
from decimal import Decimal
import sqlite3

import pandas as pd
import pytest

from app_module.market_breadth_service import (
    MarketBreadthProvider,
    MarketBreadthService,
    SQLiteDailyPriceMarketBreadthProvider,
)
from app_module.decision_desk_dtos import DecisionDeskQuality
from app_module.exceptions import BacktestCancelledError


class FakeMarketBreadthProvider:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame

    def fetch(self, as_of_date: date) -> pd.DataFrame:
        return self.frame.copy()


class BrokenMarketBreadthProvider:
    def fetch(self, as_of_date: date) -> pd.DataFrame:
        raise RuntimeError("provider temporary unavailable")


def _reference_new_extreme_count(
    data: pd.DataFrame,
    current: pd.DataFrame,
    actual_key: str,
    window: int,
    direction: str,
) -> int | None:
    keys = sorted(key for key in data["_date_key"].dropna().unique() if key <= actual_key)
    window_keys = keys[-window:]
    if len(window_keys) < window:
        return None
    history = data.loc[data["_date_key"].isin(window_keys)].dropna(
        subset=["證券代號", "_close"]
    )
    if history.empty:
        return None

    count = 0
    for _, row in current.iterrows():
        stock_code = row["證券代號"]
        current_close = row["_close"]
        stock_history = history.loc[history["證券代號"] == stock_code, "_close"]
        if stock_history.empty or current_close is None:
            continue
        extreme = max(stock_history) if direction == "high" else min(stock_history)
        if current_close == extreme:
            count += 1
    return count


def test_market_breadth_service_builds_summary_from_df_with_injected_provider():
    frame = pd.DataFrame(
        {
            "as_of_date": ["2026-06-14", "20260615", "2026-06-16"],
            "advancing": [48, 63, 70],
            "declining": [52, 37, 30],
            "unchanged": [10, 0, 5],
        }
    )
    service = MarketBreadthService(FakeMarketBreadthProvider(frame))
    snapshot = service.build_snapshot(date(2026, 6, 15), cancel_callback=lambda: False)

    assert snapshot.quality == DecisionDeskQuality.OBSERVED
    assert snapshot.as_of_date == date(2026, 6, 15)
    assert snapshot.advancing == 63
    assert snapshot.declining == 37
    assert snapshot.breadth_ratio_bp == 6300
    assert snapshot.warnings == ()


def test_market_breadth_service_returns_missing_when_no_match():
    frame = pd.DataFrame(
        {
            "date": ["2026-06-01", "20260614"],
            "advancing": [50, 60],
            "declining": [50, 40],
        }
    )
    service = MarketBreadthService(FakeMarketBreadthProvider(frame))
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.MISSING
    assert snapshot.warnings == ("market_breadth_missing",)
    assert snapshot.breadth_ratio_bp is None


def test_market_breadth_service_can_match_target_with_partial_invalid_dates():
    frame = pd.DataFrame(
        {
            "as_of_date": ["bad-date", "20260615", None],
            "advancing": [40, 60, 80],
            "declining": [60, 40, 20],
        }
    )
    service = MarketBreadthService(FakeMarketBreadthProvider(frame))
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.OBSERVED
    assert snapshot.as_of_date == date(2026, 6, 15)
    assert snapshot.advancing == 60
    assert snapshot.declining == 40
    assert snapshot.breadth_ratio_bp == 6000
    assert snapshot.warnings == ()


def test_market_breadth_service_returns_degraded_on_invalid_date_format():
    frame = pd.DataFrame(
        {
            "trade_date": ["202606", "20260613"],
            "advancing_count": [10, 20],
            "declining_count": [10, 25],
        }
    )
    service = MarketBreadthService(FakeMarketBreadthProvider(frame))
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.MISSING
    assert snapshot.warnings == ("market_breadth_missing",)


def test_market_breadth_service_returns_degraded_on_provider_error():
    service = MarketBreadthService(BrokenMarketBreadthProvider())
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.DEGRADED
    assert snapshot.advancing is None
    assert any("provider temporary unavailable" in w for w in snapshot.warnings)


def test_market_breadth_service_handles_non_contiguous_index_and_matches_target_date():
    frame = pd.DataFrame(
        {
            "as_of_date": ["2026-06-14", "20260615", "2026-06-16"],
            "advancing": [48, 63, 70],
            "declining": [52, 37, 30],
            "unchanged": [10, 0, 5],
        }
    )
    frame.index = [10, 20, 30]

    service = MarketBreadthService(FakeMarketBreadthProvider(frame))
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.OBSERVED
    assert snapshot.as_of_date == date(2026, 6, 15)
    assert snapshot.advancing == 63
    assert snapshot.declining == 37
    assert snapshot.breadth_ratio_bp == 6300
    assert snapshot.warnings == ()


def test_sqlite_daily_price_provider_builds_market_breadth_from_daily_prices(tmp_path):
    db_path = tmp_path / "twstock.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE daily_prices (
                日期 TEXT,
                證券代號 TEXT,
                收盤價 REAL,
                漲跌價差 REAL,
                成交股數 INTEGER,
                "漲跌(+/-)" TEXT,
                PRIMARY KEY (證券代號, 日期)
            )
            """
        )
        conn.executemany(
            "INSERT INTO daily_prices (日期, 證券代號, 收盤價, 漲跌價差, 成交股數, \"漲跌(+/-)\") VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("20260612", "2330", 100, 1, 1_000, "+"),
                ("20260612", "2317", 50, -1, 2_000, "-"),
                ("20260612", "2454", 75, 0, 1_000, ""),
                ("20260615", "2330", 110, 10, 3_000, "+"),
                ("20260615", "2317", 49, -1, 1_000, "-"),
                ("20260615", "2454", 75, 0, 2_000, ""),
            ],
        )

    service = MarketBreadthService(SQLiteDailyPriceMarketBreadthProvider(db_path))
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.OBSERVED
    assert snapshot.advancing == 1
    assert snapshot.declining == 1
    assert snapshot.unchanged == 1
    assert snapshot.breadth_ratio_bp == 5000
    assert snapshot.meta["source"] == "sqlite_daily_prices"
    assert snapshot.meta["volume_expansion_bp"] == 15000
    assert snapshot.meta["limit_up_count"] == 1


def test_sqlite_daily_price_provider_uses_latest_available_date_with_warning(tmp_path):
    db_path = tmp_path / "twstock.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE daily_prices (
                日期 TEXT,
                證券代號 TEXT,
                收盤價 REAL,
                漲跌價差 REAL,
                成交股數 INTEGER,
                "漲跌(+/-)" TEXT,
                PRIMARY KEY (證券代號, 日期)
            )
            """
        )
        conn.executemany(
            "INSERT INTO daily_prices (日期, 證券代號, 收盤價, 漲跌價差, 成交股數, \"漲跌(+/-)\") VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("20260612", "2330", 100, 1, 1_000, "+"),
                ("20260612", "2317", 50, -1, 2_000, "-"),
            ],
        )

    service = MarketBreadthService(SQLiteDailyPriceMarketBreadthProvider(db_path))
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.DEGRADED
    assert snapshot.as_of_date == date(2026, 6, 12)
    assert snapshot.advancing == 1
    assert snapshot.declining == 1
    assert "market_breadth_as_of_fallback:2026-06-12" in snapshot.warnings


def test_sqlite_provider_uses_explicit_direction_for_absolute_source_change(tmp_path):
    db_path = tmp_path / "direction.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE daily_prices (
                日期 TEXT,
                證券代號 TEXT,
                收盤價 TEXT,
                漲跌價差 TEXT,
                成交股數 INTEGER,
                "漲跌(+/-)" TEXT,
                PRIMARY KEY (證券代號, 日期)
            )
            """
        )
        conn.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("20260612", "2330", "100", "1", 1000, "+"),
                ("20260612", "2317", "100", "1", 1000, "+"),
                ("20260612", "2454", "100", "0", 1000, ""),
                ("20260615", "2330", "95", "5", 1000, "-"),
                ("20260615", "2317", "105", "5", 1000, "+"),
                ("20260615", "2454", "100", "1", 1000, "除權"),
            ],
        )

    snapshot = MarketBreadthService(
        SQLiteDailyPriceMarketBreadthProvider(db_path)
    ).build_snapshot(date(2026, 6, 15))

    assert snapshot.advancing == 1
    assert snapshot.declining == 1
    assert snapshot.unchanged == 0
    assert snapshot.quality == DecisionDeskQuality.DEGRADED
    assert "market_breadth_skipped_rows:1" in snapshot.warnings


def test_sqlite_provider_skips_unclassified_row_without_close_difference_fallback(tmp_path):
    db_path = tmp_path / "unclassified-direction.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE daily_prices (
                日期 TEXT,
                證券代號 TEXT,
                收盤價 TEXT,
                漲跌價差 TEXT,
                成交股數 INTEGER,
                "漲跌(+/-)" TEXT,
                PRIMARY KEY (證券代號, 日期)
            )
            """
        )
        previous_rows = [
            ("20261001", f"QA{index:04d}", "100", "0", 1000, "")
            for index in range(1962)
        ]
        current_rows: list[tuple[str, str, str, str | None, int, str | None]] = []
        for index in range(941):
            current_rows.append(
                ("20261002", f"QA{index:04d}", "101", "1", 1000, "+")
            )
        for index in range(941, 941 + 841):
            current_rows.append(
                ("20261002", f"QA{index:04d}", "99", "-1", 1000, "-")
            )
        for index in range(941 + 841, 941 + 841 + 179):
            current_rows.append(
                ("20261002", f"QA{index:04d}", "100", "0", 1000, "")
            )
        current_rows.append(
            ("20261002", "QA1961", "90", None, 1000, None)
        )
        conn.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?)",
            previous_rows + current_rows,
        )

    snapshot = MarketBreadthService(
        SQLiteDailyPriceMarketBreadthProvider(db_path)
    ).build_snapshot(date(2026, 10, 2))

    assert snapshot.quality == DecisionDeskQuality.DEGRADED
    assert snapshot.advancing == 941
    assert snapshot.declining == 841
    assert snapshot.unchanged == 179
    assert snapshot.breadth_ratio_bp == 5280
    assert snapshot.meta["stock_count"] == 1962
    assert "market_breadth_skipped_rows:1" in snapshot.warnings


def test_new_extreme_count_matches_reference_for_ties_missing_dates_and_window_bounds():
    rows = [
        ("20261001", "A", Decimal("1")),
        ("20261002", "A", Decimal("100")),
        ("20261003", "A", Decimal("110")),
        ("20261003", "A", Decimal("110")),
        ("20261004", "A", Decimal("110")),
        ("20261005", "A", Decimal("999")),
        ("20261002", "B", Decimal("90")),
        ("20261003", "B", Decimal("80")),
        ("20261004", "B", Decimal("80")),
        ("20261002", "C", Decimal("50")),
        ("20261003", "C", None),
        ("20261004", "C", Decimal("55")),
        ("20261001", "D", Decimal("1")),
        ("20261002", "D", Decimal("10")),
        ("20261003", "D", Decimal("12")),
        ("20261004", "D", Decimal("12")),
        ("20261002", "E", Decimal("10")),
        ("20261003", "E", Decimal("9")),
        ("20261004", "E", Decimal("9")),
        ("20261005", "E", Decimal("0")),
        ("20261002", "F", Decimal("9")),
        ("20261003", "F", Decimal("12")),
        ("20261004", "F", Decimal("10")),
        ("20261002", "G", Decimal("10")),
        ("20261003", "G", Decimal("13")),
        ("20261004", "G", Decimal("12")),
        ("20261005", "G", Decimal("1000")),
        ("20261001", "H", Decimal("1")),
        ("20261002", "H", Decimal("5")),
        ("20261003", "H", Decimal("5")),
        ("20261004", "H", Decimal("5")),
        ("20261002", None, Decimal("5")),
    ]
    data = pd.DataFrame(rows, columns=["_date_key", "證券代號", "_close"])
    current = data.loc[data["_date_key"] == "20261004"].copy()
    current = pd.concat(
        [
            current,
            pd.DataFrame(
                [("20261004", "NO_HISTORY", Decimal("1"))],
                columns=["_date_key", "證券代號", "_close"],
            ),
        ],
        ignore_index=True,
    )

    for direction, expected in (("high", 4), ("low", 3)):
        actual = SQLiteDailyPriceMarketBreadthProvider._new_extreme_count(
            data, current, "20261004", 3, direction
        )
        assert actual == expected
        assert actual == _reference_new_extreme_count(
            data, current, "20261004", 3, direction
        )

    # The older outlier H is outside a three-session window, but inside four.
    assert SQLiteDailyPriceMarketBreadthProvider._new_extreme_count(
        data, current, "20261004", 4, "low"
    ) == 2
    assert SQLiteDailyPriceMarketBreadthProvider._new_extreme_count(
        data, current, "20261004", 4, "low"
    ) == _reference_new_extreme_count(data, current, "20261004", 4, "low")
    # Only four distinct dates are available at the cutoff; future rows do not
    # satisfy a five-session window.
    assert SQLiteDailyPriceMarketBreadthProvider._new_extreme_count(
        data, current, "20261004", 5, "high"
    ) is None


def test_sqlite_market_breadth_cancellation_during_select_allows_same_provider_retry(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "breadth-cancel.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            '''
            CREATE TABLE daily_prices (
                "日期" TEXT,
                "證券代號" TEXT,
                "收盤價" REAL,
                "漲跌價差" REAL,
                "成交股數" INTEGER,
                "漲跌(+/-)" TEXT
            )
            '''
        )
        connection.executemany(
            'INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?)',
            [
                ("20260612", "2330", 100, 1, 1000, "+"),
                ("20260615", "2330", 101, 1, 1100, "+"),
            ],
        )

    provider = SQLiteDailyPriceMarketBreadthProvider(db_path, lookback_days=3)
    provider.SQLITE_CANCEL_CHECK_INTERVAL = 1
    cancel_state = {"requested": False}
    original_read_sql_query = pd.read_sql_query

    def trace_select(query, connection, *args, **kwargs):
        def observe(statement: str) -> None:
            if "SELECT DISTINCT" in statement.upper() and "DAILY_PRICES" in statement.upper():
                cancel_state["requested"] = True

        connection.set_trace_callback(observe)
        return original_read_sql_query(query, connection, *args, **kwargs)

    monkeypatch.setattr(pd, "read_sql_query", trace_select)
    with pytest.raises(BacktestCancelledError):
        provider.fetch(date(2026, 6, 15), cancel_callback=lambda: cancel_state["requested"])

    assert cancel_state["requested"] is True
    monkeypatch.setattr(pd, "read_sql_query", original_read_sql_query)
    frame = provider.fetch(date(2026, 6, 15))
    assert not frame.empty


def test_sqlite_market_breadth_does_not_mask_database_error_as_cancellation(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "breadth-db-error.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            'CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "收盤價" REAL, "漲跌" REAL, "成交股數" INTEGER)'
        )
        connection.execute(
            'INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?)',
            ("20260615", "2330", 101, 1, 1000),
        )

    requested = {"value": False}

    def unrelated_database_error(*_args, **_kwargs):
        requested["value"] = True
        raise pd.errors.DatabaseError("unrelated query failure")

    monkeypatch.setattr(pd, "read_sql_query", unrelated_database_error)
    provider = SQLiteDailyPriceMarketBreadthProvider(db_path)
    with pytest.raises(pd.errors.DatabaseError, match="unrelated query failure"):
        provider.fetch(date(2026, 6, 15), cancel_callback=lambda: requested["value"])
