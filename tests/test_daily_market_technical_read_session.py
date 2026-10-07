"""驗證多股技術來源共享唯讀 SQLite snapshot 的隔離契約。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, datetime, time, timedelta
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

import app_module.daily_market_technical_read_session as read_session_module
import app_module.daily_market_technical_source as source_adapter
from app_module.daily_market_technical_read_session import (
    DAILY_MARKET_TECHNICAL_READ_SESSION_BATCH_MAX_STOCKS,
    DAILY_MARKET_TECHNICAL_READ_SESSION_MAX_STOCKS,
    DailyMarketTechnicalReadSession,
    DailyMarketTechnicalSourceClockV4,
)
from app_module.daily_market_technical_source import (
    DailyMarketTechnicalSourceError,
    load_daily_market_technical_window,
)
from app_module.sqlite_read_only import ReadOperationCancelled


_TAIPEI = ZoneInfo("Asia/Taipei")
_START_DATE = date(2026, 7, 1)
_SESSION_CLOSE = 139


def _short_temp() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(
        prefix=".trs-",
        dir=Path(__file__).resolve().parents[1],
    )


def _cutoff(day: date) -> datetime:
    return datetime.combine(day, time(16, 0), tzinfo=_TAIPEI)


def _write_multistock_source(
    path: Path,
    stock_codes: tuple[str, ...],
    *,
    rows_per_stock: int = 40,
    wal: bool = False,
) -> None:
    connection = sqlite3.connect(path)
    try:
        if wal:
            connection.execute("PRAGMA journal_mode=WAL")
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            rows: list[tuple[str, str, str, str, str, str, int]] = []
            for stock_code in stock_codes:
                for offset in range(rows_per_stock):
                    close = 100 + offset
                    day = _START_DATE + timedelta(days=offset)
                    rows.append((
                        day.isoformat(),
                        stock_code,
                        str(close),
                        str(close + 1),
                        str(close - 1),
                        str(close),
                        1000 + offset,
                    ))
            connection.executemany(
                "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
                rows,
            )
    finally:
        connection.close()


def _capture_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[sqlite3.Connection], list[str]]:
    connections: list[sqlite3.Connection] = []
    statements: list[str] = []
    original_connect = read_session_module.connect_read_only_sqlite

    def connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection = original_connect(*args, **kwargs)
        connections.append(connection)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(read_session_module, "connect_read_only_sqlite", connect)
    return connections, statements


def _assert_connection_closed(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_17_stock_windows_share_one_query_only_snapshot_across_two_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stock_codes = tuple(f"S{index:04d}" for index in range(17))
    assert DAILY_MARKET_TECHNICAL_READ_SESSION_BATCH_MAX_STOCKS == 16
    assert DAILY_MARKET_TECHNICAL_READ_SESSION_MAX_STOCKS >= len(stock_codes)
    with _short_temp() as root_text:
        database = Path(root_text) / "prices.sqlite"
        _write_multistock_source(database, stock_codes)
        before_bytes = database.read_bytes()
        connections, statements = _capture_connection(monkeypatch)
        resolve_calls = 0
        original_resolve = source_adapter._resolve_source_columns

        def resolve_once(columns: tuple[str, ...]) -> dict[str, str | None]:
            nonlocal resolve_calls
            resolve_calls += 1
            return original_resolve(columns)

        monkeypatch.setattr(source_adapter, "_resolve_source_columns", resolve_once)
        decision_cutoff = _cutoff(_START_DATE + timedelta(days=39))

        with DailyMarketTechnicalReadSession(database, decision_cutoff) as session:
            clock = session.clock
            session.load_batch(stock_codes[:16])
            assert len(connections) == 1
            assert connections[0].in_transaction is True
            assert int(connections[0].execute("PRAGMA query_only").fetchone()[0]) == 1
            session.load_batch(stock_codes[16:])
            assert len(connections) == 1
            assert connections[0].in_transaction is True
            assert session.loaded_stock_codes == stock_codes
            windows = session.finish()

        assert resolve_calls == 1
        assert len(connections) == 1
        assert statements.count("BEGIN") == 1
        assert sum(statement.startswith("SELECT") for statement in statements) == 17
        assert sum('PRAGMA table_info("daily_prices")' in statement for statement in statements) == 1
        _assert_connection_closed(connections[0])
        assert database.read_bytes() == before_bytes
        assert tuple(window.stock_code for window in windows) == stock_codes
        assert all(len(window.rows) == 40 for window in windows)
        assert all(window.source_pin_sha256 == clock.source_pin_sha256 for window in windows)
        assert all(window.schema_identity_sha256 == clock.schema_identity_sha256 for window in windows)
        assert all(window.decision_cutoff == decision_cutoff for window in windows)
        assert all(window.source_available_at is None for window in windows)
        assert all(window.availability_status == "unknown" for window in windows)
        with pytest.raises(FrozenInstanceError):
            windows[0].stock_code = "mutated"  # type: ignore[misc]

        assert set(clock.to_dict()) == {
            "database_path",
            "source_id",
            "schema_identity_sha256",
            "source_file_pin",
            "source_pin_sha256",
            "decision_date",
            "decision_cutoff",
            "cutoff_guard_version",
            "source_available_at",
            "availability_status",
            "historical_pit_eligible",
        }
        assert clock.to_dict()["source_available_at"] is None
        assert clock.to_dict()["availability_status"] == "unknown"
        assert clock.to_dict()["historical_pit_eligible"] is False

        single_window = load_daily_market_technical_window(
            database,
            stock_codes[0],
            decision_cutoff,
        )
        assert single_window.to_dict() == windows[0].to_dict()
        assert single_window.source_identity == windows[0].source_identity
        assert single_window.calculation_identity_sha256 == windows[0].calculation_identity_sha256


@pytest.mark.parametrize("mutation", ("update", "rollback", "schema"))
def test_source_wal_or_schema_change_after_first_batch_fails_closed(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stock_codes = tuple(f"S{index:04d}" for index in range(17))
    with _short_temp() as root_text:
        database = Path(root_text) / "prices.sqlite"
        _write_multistock_source(database, stock_codes, wal=True)
        connections, _statements = _capture_connection(monkeypatch)
        decision_cutoff = _cutoff(_START_DATE + timedelta(days=39))

        with pytest.raises(DailyMarketTechnicalSourceError) as error_info:
            with DailyMarketTechnicalReadSession(database, decision_cutoff) as session:
                initial_clock = session.clock
                session.load_batch(stock_codes[:16])
                writer = sqlite3.connect(database)
                try:
                    if mutation == "update":
                        writer.execute(
                            "UPDATE daily_prices SET 收盤價='999' WHERE 證券代號=? AND 日期=?",
                            (stock_codes[16], (_START_DATE + timedelta(days=39)).isoformat()),
                        )
                        writer.commit()
                    elif mutation == "rollback":
                        date_token = (_START_DATE + timedelta(days=39)).isoformat()
                        writer.execute(
                            "UPDATE daily_prices SET 收盤價='999' WHERE 證券代號=? AND 日期=?",
                            (stock_codes[16], date_token),
                        )
                        writer.commit()
                        writer.execute(
                            "UPDATE daily_prices SET 收盤價=? WHERE 證券代號=? AND 日期=?",
                            (str(_SESSION_CLOSE), stock_codes[16], date_token),
                        )
                        writer.commit()
                    else:
                        writer.execute(
                            "ALTER TABLE daily_prices ADD COLUMN source_revision TEXT"
                        )
                        writer.commit()
                finally:
                    writer.close()

                session.load_batch(stock_codes[16:])
                # 第二批仍使用第一批開啟的 SQLite snapshot 與快取 alias map。
                latest_raw = session._raw_windows[-1][1][0]
                assert latest_raw["收盤價"] == str(_SESSION_CLOSE)
                if mutation == "schema":
                    assert "source_revision" not in latest_raw.keys()
                assert session.clock.identity_sha256 == initial_clock.identity_sha256
                session.finish()

        assert error_info.value.code == "daily_technical_source_changed_during_read"
        assert len(connections) == 1
        _assert_connection_closed(connections[0])


def test_duplicate_batch_error_is_preserved_and_connection_always_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stock_codes = ("S0000",)
    with _short_temp() as root_text:
        database = Path(root_text) / "prices.sqlite"
        _write_multistock_source(database, stock_codes)
        connections, _statements = _capture_connection(monkeypatch)
        with pytest.raises(DailyMarketTechnicalSourceError) as error_info:
            with DailyMarketTechnicalReadSession(
                database,
                _cutoff(_START_DATE + timedelta(days=39)),
            ) as session:
                session.load_batch((stock_codes[0], stock_codes[0]))
        assert error_info.value.code == "daily_technical_read_session_duplicate_stock"
        assert len(connections) == 1
        _assert_connection_closed(connections[0])


def test_original_context_exception_is_not_masked_and_connection_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _short_temp() as root_text:
        database = Path(root_text) / "prices.sqlite"
        _write_multistock_source(database, ("S0000",))
        connections, _statements = _capture_connection(monkeypatch)
        with pytest.raises(RuntimeError, match="original session failure"):
            with DailyMarketTechnicalReadSession(
                database,
                _cutoff(_START_DATE + timedelta(days=39)),
            ):
                raise RuntimeError("original session failure")
        assert len(connections) == 1
        _assert_connection_closed(connections[0])


def test_late_cancellation_discards_loaded_rows_and_closes_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancelled = False

    def cancellation_requested() -> bool:
        return cancelled

    with _short_temp() as root_text:
        database = Path(root_text) / "prices.sqlite"
        _write_multistock_source(database, ("S0000",))
        connections, _statements = _capture_connection(monkeypatch)
        with pytest.raises(ReadOperationCancelled):
            with DailyMarketTechnicalReadSession(
                database,
                _cutoff(_START_DATE + timedelta(days=39)),
                cancel_callback=cancellation_requested,
            ) as session:
                session.load_batch(("S0000",))
                cancelled = True
                session.finish()
        assert len(connections) == 1
        _assert_connection_closed(connections[0])


def test_source_clock_rejects_wrong_pin_and_wrong_taipei_date() -> None:
    canonical_path = str(Path("C:/fixture/prices.sqlite").resolve())
    pin: tuple[tuple[str, int, int, int, int] | tuple[str], ...] = (
        (canonical_path, 1, 2, 3, 4),
        (f"{canonical_path}-wal",),
    )
    pin_sha256 = source_adapter._sha256_json([list(item) for item in pin])

    def build_clock(
        *,
        source_pin_sha256: str = pin_sha256,
        decision_date: date = date(2026, 8, 9),
    ) -> DailyMarketTechnicalSourceClockV4:
        return DailyMarketTechnicalSourceClockV4(
            database_path=canonical_path,
            schema_identity_sha256="a" * 64,
            source_file_pin=pin,
            source_pin_sha256=source_pin_sha256,
            decision_date=decision_date,
            decision_cutoff=_cutoff(date(2026, 8, 9)),
            cutoff_guard_version=source_adapter.DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
        )

    clock = build_clock()
    assert clock.to_dict()["decision_date"] == "2026-08-09"
    assert clock.identity_sha256 == source_adapter._sha256_json(clock.to_dict())

    with pytest.raises(ValueError, match="pin 指紋不符"):
        build_clock(source_pin_sha256="b" * 64)
    with pytest.raises(ValueError, match="cutoff 日期不符"):
        build_clock(decision_date=date(2026, 8, 8))
