from datetime import date, timedelta
import sqlite3

import pandas as pd
import pytest
from app_module.decision_desk_dtos import DecisionDeskQuality
from app_module.exceptions import BacktestCancelledError
from app_module.relative_strength_liquidity_service import (
    RelativeStrengthLiquidityService,
    SQLiteDailyPriceRelativeStrengthLiquidityProvider,
    _map_series_with_cancellation,
)


DATE_COL = "\u65e5\u671f"
CODE_COL = "\u8b49\u5238\u4ee3\u865f"
CLOSE_COL = "\u6536\u76e4\u50f9"
VOLUME_COL = "\u6210\u4ea4\u80a1\u6578"


class FakeProvider:
    def __init__(self, frame):
        self.frame = frame

    def fetch(self, as_of_date: date):
        return self.frame


def _row(current_date: date, stock_code: str, close: int, volume: int = 1_000_000) -> dict[str, str]:
    return {
        DATE_COL: current_date.strftime("%Y-%m-%d"),
        CODE_COL: stock_code,
        CLOSE_COL: str(close),
        VOLUME_COL: str(volume),
    }


def test_relative_strength_liquidity_service_ranks_strength_and_low_liquidity():
    # Construct 21 trading days for 3 symbols
    # We want 2330 to be top_strength, 2454 to be medium, 1101 to be weak and low_liquidity
    base_date = date(2026, 5, 10)
    data = []
    
    # 2330: price goes from 100 to 121 (21% gain)
    # 2454: price goes from 200 to 220 (10% gain)
    # 1101: price goes from 50 to 45 (10% loss), and very low volume
    for i in range(22): # 22 days to ensure len(history) >= 21
        current_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        
        # 2330
        close_2330 = 100 + i
        data.append({"日期": current_date, "證券代號": "2330", "收盤價": str(close_2330), "成交股數": "1000000"})
        
        # 2454
        close_2454 = 200 + i
        data.append({"日期": current_date, "證券代號": "2454", "收盤價": str(close_2454), "成交股數": "500000"})
        
        # 1101
        close_1101 = 50 - (i * 0.25)
        data.append({"日期": current_date, "證券代號": "1101", "收盤價": str(close_1101), "成交股數": "100"}) # 100 * 50 = 5000 (very low turnover)

    frame = pd.DataFrame(data)
    # Target date is the last day
    target_date = base_date + timedelta(days=21)
    
    service = RelativeStrengthLiquidityService(
        FakeProvider(frame),
        top_n=2,
        min_avg_turnover=20_000_000, # 20M
    )

    snapshot = service.build_snapshot(target_date, cancel_callback=lambda: False)

    assert snapshot.quality == DecisionDeskQuality.OBSERVED
    assert snapshot.top_strength_codes == ("2330", "2454")
    assert snapshot.weak_strength_codes == ("1101",)
    assert snapshot.low_liquidity_codes == ("1101",)
    
    ranking = snapshot.meta["ranking"]
    assert ranking[0]["stock_code"] == "2330"
    # strength_20d_bp: 2330: (121 - 101) / 101 * 10000 = 19.8% * 10000 = 1980 bp
    # strength_5d_bp: 2330: (121 - 116) / 116 * 10000 = 431 bp
    assert ranking[0]["strength_20d_bp"] > 0
    assert ranking[0]["strength_5d_bp"] > 0


def test_relative_strength_cancellation_aware_map_preserves_categorical_result():
    values = pd.Series(
        pd.Categorical(["strong", "weak", "strong"], categories=["strong", "weak"]),
        index=[4, 8, 12],
        name="signal",
    )
    mapper = lambda value: {"strong": "買進", "weak": "觀望"}[value]

    expected = values.map(mapper)
    actual = _map_series_with_cancellation(values, mapper, lambda: False)

    assert actual.equals(expected)
    assert actual.dtype == expected.dtype
    assert actual.index.equals(values.index)
    assert actual.name == values.name


def test_sqlite_relative_strength_cancellation_during_select_allows_same_provider_retry(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "relative-cancel.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            f'CREATE TABLE daily_prices ("{DATE_COL}" TEXT, "{CODE_COL}" TEXT, "{CLOSE_COL}" TEXT, "{VOLUME_COL}" TEXT)'
        )
        connection.executemany(
            f'INSERT INTO daily_prices VALUES (?, ?, ?, ?)',
            [
                ("2026-06-12", "2330", "100", "1000"),
                ("2026-06-15", "2330", "101", "1100"),
            ],
        )

    provider = SQLiteDailyPriceRelativeStrengthLiquidityProvider(db_path, lookback_days=3)
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


def test_sqlite_relative_strength_does_not_mask_database_error_as_cancellation(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "relative-db-error.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            f'CREATE TABLE daily_prices ("{DATE_COL}" TEXT, "{CODE_COL}" TEXT, "{CLOSE_COL}" TEXT, "{VOLUME_COL}" TEXT)'
        )
        connection.execute(
            'INSERT INTO daily_prices VALUES (?, ?, ?, ?)',
            ("2026-06-15", "2330", "101", "1000"),
        )

    requested = {"value": False}

    def unrelated_database_error(*_args, **_kwargs):
        requested["value"] = True
        raise pd.errors.DatabaseError("unrelated query failure")

    monkeypatch.setattr(pd, "read_sql_query", unrelated_database_error)
    provider = SQLiteDailyPriceRelativeStrengthLiquidityProvider(db_path)
    with pytest.raises(pd.errors.DatabaseError, match="unrelated query failure"):
        provider.fetch(date(2026, 6, 15), cancel_callback=lambda: requested["value"])


def test_relative_strength_liquidity_service_keeps_observed_for_small_partial_skips():
    base_date = date(2026, 5, 10)
    target_date = base_date + timedelta(days=21)
    data = []
    for symbol_index in range(20):
        stock_code = f"{1000 + symbol_index}"
        for day_index in range(22):
            data.append(_row(base_date + timedelta(days=day_index), stock_code, 100 + symbol_index + day_index))
    for day_index in range(10):
        data.append(_row(target_date - timedelta(days=9 - day_index), "9999", 100 + day_index))

    service = RelativeStrengthLiquidityService(FakeProvider(pd.DataFrame(data)), top_n=3)

    snapshot = service.build_snapshot(target_date)

    assert snapshot.quality == DecisionDeskQuality.OBSERVED
    assert snapshot.warnings == ("relative_strength_liquidity_skipped_symbols:1",)
    assert snapshot.meta["ranked_symbol_count"] == 20
    assert snapshot.meta["skipped_symbol_count"] == 1
    assert snapshot.meta["skipped_symbol_ratio_bp"] <= snapshot.meta["max_skipped_symbol_ratio_bp"]


def test_relative_strength_liquidity_service_degrades_when_partial_skips_exceed_tolerance():
    base_date = date(2026, 5, 10)
    target_date = base_date + timedelta(days=21)
    data = []
    for day_index in range(22):
        data.append(_row(base_date + timedelta(days=day_index), "2330", 100 + day_index))
    for day_index in range(10):
        data.append(_row(target_date - timedelta(days=9 - day_index), "9999", 100 + day_index))

    service = RelativeStrengthLiquidityService(FakeProvider(pd.DataFrame(data)), top_n=3)

    snapshot = service.build_snapshot(target_date)

    assert snapshot.quality == DecisionDeskQuality.DEGRADED
    assert snapshot.warnings == ("relative_strength_liquidity_skipped_symbols:1",)
    assert snapshot.meta["ranked_symbol_count"] == 1
    assert snapshot.meta["skipped_symbol_count"] == 1
    assert snapshot.meta["skipped_symbol_ratio_bp"] > snapshot.meta["max_skipped_symbol_ratio_bp"]


def test_relative_strength_liquidity_service_marks_degraded_when_history_is_insufficient():
    # Only 10 days of history
    base_date = date(2026, 5, 10)
    data = []
    for i in range(10):
        current_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        data.append({"日期": current_date, "證券代號": "2330", "收盤價": "100", "成交股數": "100000"})
        data.append({"日期": current_date, "證券代號": "1101", "收盤價": "50", "成交股數": "1000"})

    frame = pd.DataFrame(data)
    target_date = base_date + timedelta(days=9)
    service = RelativeStrengthLiquidityService(FakeProvider(frame), top_n=3)

    snapshot = service.build_snapshot(target_date)

    assert snapshot.quality == DecisionDeskQuality.DEGRADED
    assert snapshot.top_strength_codes == ()
    assert "relative_strength_liquidity_insufficient_history" in snapshot.warnings


def test_relative_strength_liquidity_service_missing_when_frame_has_only_future_dates():
    frame = pd.DataFrame(
        [
            {"日期": "2026-06-16", "證券代號": "2330", "收盤價": "120", "成交股數": "10000000"},
        ]
    )
    service = RelativeStrengthLiquidityService(FakeProvider(frame), top_n=3)

    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.MISSING
    assert snapshot.warnings == ("relative_strength_liquidity_missing",)
