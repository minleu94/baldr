from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from data_module import ml_historical_snapshot_provider as provider_module
from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider


def _make_database(path: Path, *, journal_mode: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        mode = connection.execute(f"PRAGMA journal_mode={journal_mode}").fetchone()
        assert mode is not None and str(mode[0]).lower() == journal_mode.lower()
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
            CREATE TABLE market_indices (日期 TEXT, 收盤指數 TEXT, 收盤價 TEXT);
            CREATE TABLE industry_indices (日期 TEXT, 指數名稱 TEXT, 收盤指數 TEXT);
            """
        )
        for day, close in (("20240101", "100"), ("20240102", "110")):
            connection.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (day, "AAA", 1000, 100000, close, close, close, close),
            )
            connection.execute(
                "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?)",
                (day, "AAA", "50", "0", "20"),
            )
            connection.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?)",
                (day, "10000", "10000"),
            )
        connection.commit()
    finally:
        connection.close()


def _provider(path: Path, monkeypatch: pytest.MonkeyPatch) -> MLHistoricalSnapshotProvider:
    monkeypatch.setattr(
        provider_module,
        "check_daily_price_source_revision",
        lambda **_kwargs: None,
    )
    return MLHistoricalSnapshotProvider(path)


def _load(lease):
    return lease.load(
        decision_date="2024-01-03",
        history_start_date="2024-01-01",
        symbols=("AAA",),
    )


def _update_close(path: Path, value: str, *, timeout: float = 0.0) -> None:
    writer = sqlite3.connect(path, timeout=timeout)
    try:
        cursor = writer.execute(
            'UPDATE daily_prices SET "收盤價" = ? '
            'WHERE "日期" = ? AND "證券代號" = ?',
            (value, "20240102", "AAA"),
        )
        assert cursor.rowcount == 1
        writer.commit()
    finally:
        writer.close()


def test_wal_read_lease_detects_external_commit_after_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "source.sqlite"
    _make_database(database, journal_mode="wal")
    provider = _provider(database, monkeypatch)

    with provider.open_read_lease() as lease:
        snapshot = _load(lease)
        assert snapshot.prices[-1].close_price is not None
        assert str(snapshot.prices[-1].close_price) == "110"
        assert lease._connection is not None
        assert lease._connection.in_transaction is False

        _update_close(database, "999")

        with pytest.raises(RuntimeError, match="changed during read lease"):
            lease.assert_unchanged()


def test_wal_read_lease_detects_write_and_restore_commits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "source.sqlite"
    _make_database(database, journal_mode="wal")
    provider = _provider(database, monkeypatch)

    with provider.open_read_lease() as lease:
        snapshot = _load(lease)
        _update_close(database, "999")
        _update_close(database, "110")

        fresh = provider.load(
            decision_date="2024-01-03",
            history_start_date="2024-01-01",
            symbols=("AAA",),
        )
        assert str(fresh.prices[-1].close_price) == "110"
        assert str(snapshot.prices[-1].close_price) == "110"
        with pytest.raises(RuntimeError, match="changed during read lease"):
            lease.assert_unchanged()


def test_delete_read_lease_does_not_hold_lock_after_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "source.sqlite"
    _make_database(database, journal_mode="delete")
    provider = _provider(database, monkeypatch)

    with provider.open_read_lease() as lease:
        snapshot = _load(lease)
        assert str(snapshot.prices[-1].close_price) == "110"
        assert lease._connection is not None
        assert lease._connection.in_transaction is False

        # timeout=0 使任何意外保留的讀取交易立即以鎖錯誤失敗，不會等待。
        _update_close(database, "999", timeout=0.0)

        with pytest.raises(RuntimeError, match="changed during read lease"):
            lease.assert_unchanged()


def test_read_lease_is_single_load_and_rejects_use_after_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "source.sqlite"
    _make_database(database, journal_mode="wal")
    provider = _provider(database, monkeypatch)
    lease = provider.open_read_lease()

    with lease:
        _load(lease)
        with pytest.raises(RuntimeError, match="already loaded"):
            _load(lease)

    with pytest.raises(RuntimeError, match="closed"):
        lease.assert_unchanged()

    with pytest.raises(RuntimeError, match="already been used"):
        with lease:
            pass
