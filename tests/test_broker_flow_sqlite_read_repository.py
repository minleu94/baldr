from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from datetime import date, timedelta

from app_module import broker_flow_sqlite_read_repository as broker_flow_repository
from app_module.broker_flow_dashboard_dtos import BrokerFlowDashboardQuery
from app_module.broker_flow_sqlite_read_repository import (
    BrokerFlowSQLiteReadRepository,
)
from app_module.smart_money_semantic_service import (
    SQLiteSmartMoneyBatchPriceProvider,
    SQLiteSmartMoneyBatchSemanticAdapter,
)


def _create_broker_db(path):
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE broker_flows (
                日期 TEXT,
                分點名稱 TEXT,
                證券代號 TEXT,
                證券名稱 TEXT,
                買進股數 INTEGER,
                賣出股數 INTEGER,
                買賣超股數 INTEGER,
                買進金額千元 INTEGER,
                賣出金額千元 INTEGER,
                買賣超金額千元 INTEGER,
                trade_type TEXT,
                lots_observed INTEGER,
                amount_observed INTEGER,
                lots_rank INTEGER,
                amount_rank INTEGER
            )
            """
        )
        rows = []
        for day_index, day in enumerate(
            ("20260626", "20260627", "20260630", "20260701", "20260702", "20260703", "20260706")
        ):
            rows.extend(
                (
                    (
                        day,
                        "branch_a",
                        "2330",
                        "台積電",
                        160_000 + day_index * 1_000,
                        20_000,
                        140_000 + day_index * 1_000,
                        1000,
                        100,
                        900,
                        "買超",
                        1,
                        1,
                        1,
                        1,
                    ),
                    (
                        day,
                        "branch_b",
                        "2317",
                        "鴻海",
                        10_500,
                        40_000,
                        -29_500,
                        100,
                        400,
                        -300,
                        "賣超",
                        1,
                        1,
                        2,
                        2,
                    ),
                )
            )
        connection.executemany(
            "INSERT INTO broker_flows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def _query(period="week"):
    return BrokerFlowDashboardQuery(
        period=period,
        scope="top_bottom",
        requested_as_of_date=date(2026, 7, 5),
        limit_per_side=50,
    )


def _create_semantic_reuse_db(path):
    dates = []
    current = date(2026, 7, 3)
    while len(dates) < 60:
        if current.weekday() < 5:
            dates.append(current)
        current -= timedelta(days=1)
    dates.reverse()
    stock_names = {"2330": "台積電", "2317": "鴻海", "2603": "長榮"}
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE broker_flows (
                日期 TEXT, 分點名稱 TEXT, 證券代號 TEXT, 證券名稱 TEXT,
                買進股數 INTEGER, 賣出股數 INTEGER, 買賣超股數 INTEGER,
                買進金額千元 INTEGER, 賣出金額千元 INTEGER, 買賣超金額千元 INTEGER,
                trade_type TEXT, lots_observed INTEGER, amount_observed INTEGER,
                lots_rank INTEGER, amount_rank INTEGER
            )
            """
        )
        connection.execute(
            "CREATE INDEX idx_broker_flows_date ON broker_flows (日期)"
        )
        connection.execute(
            "CREATE INDEX idx_broker_flows_stock ON broker_flows (證券代號)"
        )
        rows = []
        for day_index, trading_day in enumerate(dates):
            for stock_index, (stock_code, stock_name) in enumerate(stock_names.items()):
                for branch_index in range(2):
                    buy_lots = 10 + day_index % 5 + stock_index + branch_index
                    sell_lots = buy_lots - (2 if (day_index + stock_index) % 2 else 4)
                    buy_shares = buy_lots * 1000
                    sell_shares = sell_lots * 1000
                    rows.append(
                        (
                            trading_day.strftime("%Y%m%d"),
                            f"branch_{branch_index}",
                            stock_code,
                            stock_name,
                            buy_shares,
                            sell_shares,
                            buy_shares - sell_shares,
                            buy_lots * 100,
                            sell_lots * 100,
                            (buy_lots - sell_lots) * 100,
                            "買超",
                            1,
                            1,
                            branch_index + 1,
                            branch_index + 1,
                        )
                    )
        connection.executemany(
            "INSERT INTO broker_flows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        connection.execute(
            "CREATE TABLE daily_prices (證券代號 TEXT, 日期 TEXT, 收盤價 NUMERIC)"
        )
        price_rows = [
            (stock_code, trading_day.strftime("%Y%m%d"), 50 + day_index)
            for stock_code in stock_names
            for day_index, trading_day in enumerate(dates)
        ]
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?)", price_rows
        )
    return tuple(dates), tuple(stock_names)


def _semantic_event_fields(source):
    return sorted(
        (
            event.date,
            event.branch_display_name,
            event.stock_code,
            event.stock_name,
            event.net_qty,
            event.lots_quality,
        )
        for event in source.events
    )


def test_repository_missing_db_is_typed_missing_and_does_not_create_file(tmp_path):
    db_path = tmp_path / "missing.db"

    source = BrokerFlowSQLiteReadRepository(db_path).load_dashboard_source(_query())

    assert source.quality == "missing"
    assert source.events == ()
    assert source.warnings == ("broker_flow_sqlite_missing",)
    assert not db_path.exists()


def test_repository_reads_last_five_broker_dates_and_preserves_db_bytes(tmp_path):
    db_path = tmp_path / "broker.db"
    _create_broker_db(db_path)
    before_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()
    before_mtime = db_path.stat().st_mtime_ns

    source = BrokerFlowSQLiteReadRepository(db_path).load_dashboard_source(_query())

    assert source.selected_trading_dates == (
        date(2026, 6, 27),
        date(2026, 6, 30),
        date(2026, 7, 1),
        date(2026, 7, 2),
        date(2026, 7, 3),
    )
    assert {event.date for event in source.events} == {
        "2026-06-27",
        "2026-06-30",
        "2026-07-01",
        "2026-07-02",
        "2026-07-03",
    }
    observed = next(event for event in source.events if event.stock_code == "2330")
    degraded = next(event for event in source.events if event.stock_code == "2317")
    assert observed.branch_display_name == "branch_a"
    assert observed.stock_name == "台積電"
    assert (observed.buy_qty, observed.sell_qty, observed.net_qty) == (165, 20, 145)
    assert (
        observed.buy_amount_k_twd,
        observed.sell_amount_k_twd,
        observed.net_amount_k_twd,
    ) == (1000, 100, 900)
    assert observed.lots_rank == 1
    assert observed.amount_rank == 1
    assert observed.amount_observed
    assert observed.buy_qty is not None
    assert observed.lots_quality == "observed"
    assert degraded.buy_qty == 10
    assert degraded.lots_quality == "degraded"
    assert "non_board_lot_remainder_shares" in " ".join(source.warnings)
    assert source.query_count == 2
    assert source.materialized_row_count == 10
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before_hash
    assert db_path.stat().st_mtime_ns == before_mtime


def test_source_cache_key_tracks_uncheckpointed_wal_commit(tmp_path):
    db_path = tmp_path / "broker-wal.db"
    _create_broker_db(db_path)
    repository = BrokerFlowSQLiteReadRepository(db_path)

    keeper = sqlite3.connect(db_path)
    try:
        keeper.execute("PRAGMA journal_mode=WAL")
        keeper.execute("PRAGMA wal_autocheckpoint=0")
        keeper.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        key_before = repository.source_cache_key()
        main_before = db_path.stat()

        with sqlite3.connect(db_path) as writer:
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute(
                "INSERT INTO broker_flows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "20260706", "branch_c", "2603", "長榮", 1200, 200,
                    1000, 12, 2, 10, "買超", 1, 1, 3, 3,
                ),
            )

        main_after = db_path.stat()
        key_after = repository.source_cache_key()
    finally:
        keeper.close()

    assert key_before is not None
    assert key_after is not None
    assert key_after != key_before
    assert (main_after.st_size, main_after.st_mtime_ns) == (
        main_before.st_size,
        main_before.st_mtime_ns,
    )


def test_source_cache_key_is_disabled_while_rollback_journal_exists(tmp_path):
    db_path = tmp_path / "broker-journal.db"
    _create_broker_db(db_path)
    repository = BrokerFlowSQLiteReadRepository(db_path)
    writer = sqlite3.connect(db_path)
    try:
        writer.execute(
            "INSERT INTO broker_flows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "20260706", "branch_c", "2603", "長榮", 1200, 200,
                1000, 12, 2, 10, "買超", 1, 1, 3, 3,
            ),
        )
        journal_path = db_path.with_name(db_path.name + "-journal")

        assert journal_path.exists()
        assert repository.source_cache_key() is None
    finally:
        writer.rollback()
        writer.close()


def test_source_cache_key_is_disabled_when_wal_identity_cannot_be_read(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "broker-wal-identity.db"
    _create_broker_db(db_path)
    repository = BrokerFlowSQLiteReadRepository(db_path)
    original_file_identity = repository._file_identity

    def fail_wal_identity(path):
        if path.name.endswith("-wal"):
            raise PermissionError("WAL identity unavailable")
        return original_file_identity(path)

    monkeypatch.setattr(repository, "_file_identity", fail_wal_identity)

    assert repository.source_cache_key() is None


def test_repository_reuses_selected_date_parsing_for_materialized_rows(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "broker.db"
    _create_broker_db(db_path)
    repository = BrokerFlowSQLiteReadRepository(db_path)
    original_parser = broker_flow_repository._parse_date_key
    parsed_keys = []

    def count_parse(raw):
        parsed_keys.append(raw)
        return original_parser(raw)

    monkeypatch.setattr(broker_flow_repository, "_parse_date_key", count_parse)

    dashboard = repository.load_dashboard_source(_query(period="month"))

    assert dashboard.materialized_row_count == 12
    assert len(parsed_keys) == len(dashboard.selected_trading_dates) == 6

    parsed_keys.clear()
    semantic = repository.load_stock_semantic_batch(
        ("2330", "2317"), date(2026, 7, 5), trading_day_limit=20
    )

    assert semantic.materialized_row_count == 12
    assert len(parsed_keys) == len(semantic.selected_trading_dates) == 6


def test_repository_stock_and_branch_reads_push_scope_and_limit(tmp_path):
    db_path = tmp_path / "broker.db"
    _create_broker_db(db_path)
    repository = BrokerFlowSQLiteReadRepository(db_path)

    stock_source = repository.load_stock_source("2330", _query())
    branch_source = repository.load_branch_source("branch_a", _query(), limit=2)

    assert stock_source.events
    assert {event.stock_code for event in stock_source.events} == {"2330"}
    assert stock_source.materialized_row_count == 5
    assert len(branch_source.events) == 2
    assert {event.branch_system_key for event in branch_source.events} == {"branch_a"}
    assert [event.date for event in branch_source.events] == ["2026-07-03", "2026-07-02"]


def test_semantic_batch_preserves_full_batch_semantic_fields(tmp_path):
    db_path = tmp_path / "broker.db"
    _create_broker_db(db_path)
    repository = BrokerFlowSQLiteReadRepository(db_path)
    codes = ("2330", "2317")

    full = repository.load_stock_batch_source(
        codes, date(2026, 7, 5), trading_day_limit=60
    )
    bounded = repository.load_stock_semantic_batch(
        codes, date(2026, 7, 5), trading_day_limit=60
    )

    def semantic_fields(source):
        return sorted(
            (
                event.date,
                event.branch_display_name,
                event.stock_code,
                event.stock_name,
                event.net_qty,
                event.lots_quality,
            )
            for event in source.events
        )

    assert semantic_fields(bounded) == semantic_fields(full)
    assert bounded.query_count == 2
    assert bounded.materialized_row_count == full.materialized_row_count


def test_semantic_batch_reuses_dashboard_overlap_with_exact_output_parity(tmp_path):
    db_path = tmp_path / "semantic-reuse.db"
    _, codes = _create_semantic_reuse_db(db_path)
    repository = BrokerFlowSQLiteReadRepository(db_path)
    dashboard = repository.load_dashboard_source(_query(period="month"))
    source_version = repository.source_cache_key()
    decision_date = dashboard.selected_trading_dates[-1]

    full = repository.load_stock_semantic_batch(
        codes, decision_date, trading_day_limit=60
    )
    reused = repository.load_stock_semantic_batch(
        codes,
        decision_date,
        trading_day_limit=60,
        dashboard_source=dashboard,
        expected_source_version=source_version,
    )

    assert reused.selected_trading_dates == full.selected_trading_dates
    assert _semantic_event_fields(reused) == _semantic_event_fields(full)
    assert reused.materialized_row_count == full.materialized_row_count * 2 // 3

    price_provider = SQLiteSmartMoneyBatchPriceProvider(db_path)
    adapter = SQLiteSmartMoneyBatchSemanticAdapter(repository, price_provider)
    full_semantics = adapter.build_batch_semantics(codes, decision_date)
    reused_semantics = adapter.build_batch_semantics_from_dashboard(
        codes,
        decision_date,
        dashboard_source=dashboard,
        expected_source_version=repository.source_cache_key(),
    )
    assert reused_semantics == full_semantics


def test_semantic_batch_reuse_falls_back_on_source_or_date_identity_mismatch(tmp_path):
    db_path = tmp_path / "semantic-reuse-identity.db"
    _, codes = _create_semantic_reuse_db(db_path)
    repository = BrokerFlowSQLiteReadRepository(db_path)
    dashboard = repository.load_dashboard_source(_query(period="month"))
    decision_date = dashboard.selected_trading_dates[-1]
    full = repository.load_stock_semantic_batch(
        codes, decision_date, trading_day_limit=60
    )

    stale_version = repository.load_stock_semantic_batch(
        codes,
        decision_date,
        trading_day_limit=60,
        dashboard_source=dashboard,
        expected_source_version="stale-source-version",
    )
    bad_date_identity = repository.load_stock_semantic_batch(
        codes,
        decision_date,
        trading_day_limit=60,
        dashboard_source=replace(
            dashboard,
            selected_trading_dates=dashboard.selected_trading_dates[:-1],
        ),
        expected_source_version=repository.source_cache_key(),
    )

    assert _semantic_event_fields(stale_version) == _semantic_event_fields(full)
    assert _semantic_event_fields(bad_date_identity) == _semantic_event_fields(full)
    assert stale_version.materialized_row_count == full.materialized_row_count
    assert bad_date_identity.materialized_row_count == full.materialized_row_count


def test_semantic_batch_name_conflict_falls_back_for_conflicting_stock(tmp_path):
    db_path = tmp_path / "semantic-reuse-name-conflict.db"
    dates, codes = _create_semantic_reuse_db(db_path)
    cutoff = dates[-20].strftime("%Y%m%d")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE broker_flows SET 證券名稱 = ? WHERE 證券代號 = ? AND 日期 < ?",
            ("台積電舊名", "2330", cutoff),
        )

    repository = BrokerFlowSQLiteReadRepository(db_path)
    dashboard = repository.load_dashboard_source(_query(period="month"))
    decision_date = dashboard.selected_trading_dates[-1]
    source_version = repository.source_cache_key()
    full = repository.load_stock_semantic_batch(
        codes, decision_date, trading_day_limit=60
    )
    reused = repository.load_stock_semantic_batch(
        codes,
        decision_date,
        trading_day_limit=60,
        dashboard_source=dashboard,
        expected_source_version=source_version,
    )

    assert _semantic_event_fields(reused) == _semantic_event_fields(full)
    assert reused.materialized_row_count == full.materialized_row_count
    assert reused.query_count == 4


def test_repository_missing_table_is_typed_missing_without_csv_fallback(tmp_path):
    db_path = tmp_path / "empty.db"
    with sqlite3.connect(db_path):
        pass

    source = BrokerFlowSQLiteReadRepository(db_path).load_dashboard_source(_query())

    assert source.quality == "missing"
    assert source.events == ()
    assert source.warnings == ("broker_flows_table_missing",)
