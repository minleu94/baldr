from __future__ import annotations

from contextlib import contextmanager
import sqlite3

import pandas as pd
import pytest

from app_module.update_service import (
    UpdateService,
    _can_replace_full_technical_market,
    _merge_partial_technical_publications,
    _write_technical_indicator_publications,
)
from data_module.config import TWStockConfig


def _create_isolated_db() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """CREATE TABLE technical_indicators (
            日期 TEXT NOT NULL,
            證券代號 TEXT NOT NULL,
            indicator REAL,
            untouched REAL,
            PRIMARY KEY (證券代號, 日期)
        )"""
    )
    connection.executemany(
        "INSERT INTO technical_indicators (日期, 證券代號, indicator, untouched) VALUES (?, ?, ?, ?)",
        [
            ("20200102", "2330", 1.0, 11.0),
            ("20260921", "2330", 2.0, 22.0),
            ("20260921", "2317", 3.0, 33.0),
        ],
    )
    connection.commit()
    return connection


def test_partial_publications_preserve_other_stock_and_old_unpublished_rows() -> None:
    connection = _create_isolated_db()
    publication = pd.DataFrame(
        [("20260921", "2330", 20.0), ("20260922", "2330", 21.0)],
        columns=["日期", "證券代號", "indicator"],
    )

    written = _write_technical_indicator_publications(
        connection,
        publication,
        replace_market=False,
    )

    rows = connection.execute(
        "SELECT 日期, 證券代號, indicator, untouched FROM technical_indicators ORDER BY 證券代號, 日期"
    ).fetchall()
    assert written == 2
    assert rows == [
        ("20260921", "2317", 3.0, 33.0),
        ("20200102", "2330", 1.0, 11.0),
        ("20260921", "2330", 20.0, 22.0),
        ("20260922", "2330", 21.0, None),
    ]
    connection.close()


def test_partial_csv_merge_preserves_other_keys_and_unpublished_columns() -> None:
    existing = pd.DataFrame(
        [
            ("2020-01-02", "2330", 1.0, "old-only-value"),
            ("2026-09-21", "2330", 2.0, "keep-this"),
            ("2026-09-21", "2317", 3.0, "other-stock"),
        ],
        columns=["日期", "證券代號", "indicator", "untouched"],
    )
    publication = pd.DataFrame(
        [("20260921", "2330", 20.0)],
        columns=["日期", "證券代號", "indicator"],
    )

    merged = _merge_partial_technical_publications(existing, publication)

    assert len(merged) == 3
    assert merged.loc[(merged["證券代號"] == "2330") & (merged["日期"] == "2026-09-21"), "indicator"].iloc[0] == 20.0
    assert merged.loc[(merged["證券代號"] == "2330") & (merged["日期"] == "2026-09-21"), "untouched"].iloc[0] == "keep-this"
    assert merged.loc[merged["證券代號"] == "2317", "untouched"].iloc[0] == "other-stock"
    assert merged.loc[(merged["證券代號"] == "2330") & (merged["日期"] == "2020-01-02"), "untouched"].iloc[0] == "old-only-value"


def test_failed_full_market_write_rolls_back_table_delete_and_partial_insert() -> None:
    connection = _create_isolated_db()
    invalid_publication = pd.DataFrame(
        [("20260922", "2330", 99.0, 1.0)],
        columns=["日期", "證券代號", "indicator", "unknown_column"],
    )

    with pytest.raises(sqlite3.OperationalError, match="unknown_column"):
        try:
            connection.execute("BEGIN")
            _write_technical_indicator_publications(
                connection,
                invalid_publication,
                replace_market=True,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    rows = connection.execute(
        "SELECT 日期, 證券代號, indicator, untouched FROM technical_indicators ORDER BY 證券代號, 日期"
    ).fetchall()
    assert rows == [
        ("20260921", "2317", 3.0, 33.0),
        ("20200102", "2330", 1.0, 11.0),
        ("20260921", "2330", 2.0, 22.0),
    ]
    connection.close()


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_stock": "2330"},
        {"requested_start_date": "2026-01-01"},
        {"recompute_currentity": True},
        {"cancelled": True},
        {"fail_count": 1},
        {"insufficient_count": 1},
        {"success_count": 1, "total_stocks": 2, "updated_stocks": ["2330"]},
    ],
)
def test_full_table_replacement_requires_complete_uncancelled_market_run(overrides):
    arguments = {
        "force_all": True,
        "target_stock": None,
        "requested_start_date": None,
        "recompute_currentity": False,
        "cancelled": False,
        "success_count": 2,
        "fail_count": 0,
        "insufficient_count": 0,
        "total_stocks": 2,
        "updated_stocks": ["2330", "2317"],
    }
    arguments.update(overrides)

    assert _can_replace_full_technical_market(**arguments) is False


def test_complete_force_all_market_run_may_replace_table():
    assert _can_replace_full_technical_market(
        force_all=True,
        target_stock=None,
        requested_start_date=None,
        recompute_currentity=False,
        cancelled=False,
        success_count=2,
        fail_count=0,
        insufficient_count=0,
        total_stocks=2,
        updated_stocks=["2330", "2317"],
    ) is True


@pytest.mark.parametrize(
    ("recompute_currentity", "force_all", "start_date_mode", "expected_publish_rows"),
    [
        (False, False, None, 17),
        (True, False, None, 7),
        (False, True, None, 150),
        (False, False, "explicit", 10),
    ],
)
def test_service_calculates_full_prefix_before_bounded_publication(
    tmp_path,
    monkeypatch,
    recompute_currentity,
    force_all,
    start_date_mode,
    expected_publish_rows,
):
    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "artifacts",
        profile="causal_publication_test",
    )
    config.use_sqlite = False
    config.min_data_days = 1
    dates = pd.bdate_range("2025-01-01", periods=150)
    closes = 100.0 + pd.Series(range(len(dates)), dtype=float) / 4
    source = pd.DataFrame(
        {
            "日期": dates.strftime("%Y%m%d"),
            "證券代號": "2330",
            "開盤價": closes - 0.2,
            "最高價": closes + 1,
            "最低價": closes - 1,
            "收盤價": closes,
            "成交股數": 1000,
        }
    )
    source.to_csv(config.stock_data_file, index=False, encoding="utf-8-sig")
    pd.DataFrame({"日期": [dates[139].strftime("%Y-%m-%d")]}).to_csv(
        config.technical_dir / "2330_indicators.csv",
        index=False,
        encoding="utf-8-sig",
    )
    observed = {}

    class FakeCalculator:
        def __init__(self, logger=None):
            self.logger = logger

        def calculate_all_indicators(self, frame, stock_id):
            observed["compute_rows"] = len(frame)
            result = frame.copy()
            result["test_indicator"] = range(len(result))
            return result

        def calculate_and_store_indicators(
            self,
            frame,
            stock_id,
            output_dir,
            ignore_existing=False,
            precomputed_result=None,
        ):
            observed["publish_rows"] = len(frame)
            observed["publish_first_date"] = frame["日期"].iloc[0]
            observed["result_rows"] = len(precomputed_result)
            return precomputed_result.copy()

    monkeypatch.setattr(
        "analysis_module.technical_analysis.technical_indicators.TechnicalIndicatorCalculator",
        FakeCalculator,
    )
    result = UpdateService(config).calculate_technical_indicators(
        force_all=force_all,
        start_date=(dates[139].strftime("%Y-%m-%d") if start_date_mode else None),
        incremental_lookback_days=7,
        technical_process_pool=False,
        recompute_currentity=recompute_currentity,
    )

    assert result["success"] is True
    assert observed["compute_rows"] == 150
    assert observed["publish_rows"] == expected_publish_rows
    assert observed["result_rows"] == expected_publish_rows


def test_targeted_force_all_preserves_other_stocks_in_aggregate_csv(
    tmp_path,
    monkeypatch,
):
    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "artifacts",
        profile="partial_aggregate_test",
    )
    config.use_sqlite = False
    config.min_data_days = 1
    dates = pd.bdate_range("2026-01-01", periods=5)
    closes = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0])
    source = pd.DataFrame(
        {
            "日期": dates.strftime("%Y%m%d"),
            "證券代號": "2330",
            "開盤價": closes - 0.2,
            "最高價": closes + 1,
            "最低價": closes - 1,
            "收盤價": closes,
            "成交股數": 1000,
        }
    )
    source.to_csv(config.stock_data_file, index=False, encoding="utf-8-sig")
    existing = pd.DataFrame(
        [
            ("2025-12-31", "2317", 50.0, "other"),
            (dates[-1].strftime("%Y-%m-%d"), "2330", 80.0, "keep"),
        ],
        columns=["日期", "證券代號", "test_indicator", "untouched"],
    )
    existing.to_csv(config.all_stocks_data_file, index=False, encoding="utf-8-sig")

    class FakeCalculator:
        def __init__(self, logger=None):
            self.logger = logger

        def calculate_all_indicators(self, frame, stock_id):
            result = frame.copy()
            result["test_indicator"] = 999.0
            return result

        def calculate_and_store_indicators(
            self,
            frame,
            stock_id,
            output_dir,
            ignore_existing=False,
            precomputed_result=None,
        ):
            return precomputed_result.copy()

    monkeypatch.setattr(
        "analysis_module.technical_analysis.technical_indicators.TechnicalIndicatorCalculator",
        FakeCalculator,
    )
    result = UpdateService(config).calculate_technical_indicators(
        target_stock="2330",
        force_all=True,
        technical_process_pool=False,
    )

    aggregate = pd.read_csv(config.all_stocks_data_file, dtype={"證券代號": str})
    assert result["success"] is True
    assert set(aggregate["證券代號"]) == {"2317", "2330"}
    other_stock = aggregate.loc[aggregate["證券代號"] == "2317"].iloc[0]
    assert other_stock["test_indicator"] == 50.0
    assert other_stock["untouched"] == "other"
    target = aggregate.loc[
        (aggregate["證券代號"] == "2330")
        & (aggregate["日期"] == dates[-1].strftime("%Y-%m-%d"))
    ].iloc[0]
    assert target["test_indicator"] == 999.0
    assert target["untouched"] == "keep"


def test_sqlite_publication_failure_is_reported_as_unsuccessful(
    tmp_path,
    monkeypatch,
):
    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "artifacts",
        profile="failed_sqlite_publication_test",
    )
    config.use_sqlite = True
    config.min_data_days = 1
    dates = pd.bdate_range("2026-02-02", periods=5)
    closes = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0])
    source = pd.DataFrame(
        {
            "日期": dates.strftime("%Y%m%d"),
            "證券代號": "2330",
            "開盤價": closes - 0.2,
            "最高價": closes + 1,
            "最低價": closes - 1,
            "收盤價": closes,
            "成交股數": 1000,
        }
    )

    class FakeConnection:
        def execute(self, _statement):
            return None

        def executemany(self, _statement, _values):
            raise sqlite3.OperationalError("injected publication failure")

    class FakeDBManager:
        def __init__(self, _config):
            pass

        def execute_query(self, query):
            if query.startswith("PRAGMA table_info"):
                return pd.DataFrame({"name": ["日期", "證券代號"]})
            return source.copy()

        def ensure_columns(self, _table, _columns):
            return None

        @contextmanager
        def connect(self):
            yield FakeConnection()

    class FakeCalculator:
        def __init__(self, logger=None):
            self.logger = logger

        def calculate_all_indicators(self, frame, stock_id):
            result = frame.copy()
            result["test_indicator"] = 1.0
            return result

        def calculate_and_store_indicators(
            self,
            frame,
            stock_id,
            output_dir,
            ignore_existing=False,
            precomputed_result=None,
        ):
            return precomputed_result.copy()

    monkeypatch.setattr("data_module.db_manager.DBManager", FakeDBManager)
    monkeypatch.setattr(
        "analysis_module.technical_analysis.technical_indicators.TechnicalIndicatorCalculator",
        FakeCalculator,
    )
    result = UpdateService(config).calculate_technical_indicators(
        force_all=True,
        technical_process_pool=False,
    )

    assert result["success"] is False
    assert result["sqlite_write_failed"] is True
