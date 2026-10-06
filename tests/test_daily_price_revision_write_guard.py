from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from data_module.daily_price_revision_write_guard import (
    DailyPriceRevisionWriteError,
    DailyPriceRevisionWriteGuard,
    prepare_daily_price_revision_frame,
)
from data_module.ml_daily_price_revision_gate import (
    REPAIR_RECEIPT_RELATIVE_DIR,
    REPAIR_SCHEMA,
)
from data_module.historical_session_revision import RECEIPT_DIR as SESSION_RECEIPT_DIR
from app_module.update_service import UpdateService
from scripts import migrate_csv_to_sqlite


UPDATE_COLUMNS = [
    "證券名稱",
    "成交股數",
    "成交筆數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌(+/-)",
    "漲跌",
    "涨跌",
    "漲跌價差",
    "最後揭示買價",
    "最後揭示買量",
    "最後揭示賣價",
    "最後揭示賣量",
    "本益比",
]


def test_verified_wrong_date_keys_cannot_be_reintroduced(tmp_path, monkeypatch):
    from data_module import excluded_daily_price_revision
    monkeypatch.setattr(excluded_daily_price_revision, 'load_exclusion_evidence', lambda _: [{'keys': [('20260520','0054')], 'closed_dates': ['20241002']}])
    database = tmp_path/'sqlite/twstock.db'
    bad = pd.DataFrame({'日期':['2026-05-20'],'證券代號':[54], '收盤價':[23]})
    with pytest.raises(DailyPriceRevisionWriteError, match='已核驗排除'):
        prepare_daily_price_revision_frame(database,bad)
    good = pd.DataFrame({'日期':['20260519','20260520'],'證券代號':['0054','1256'], '收盤價':[23,183]})
    assert prepare_daily_price_revision_frame(database,good).equals(good)
    closed = pd.DataFrame({'日期':['20241002'],'證券代號':['9999'], '收盤價':[23]})
    with pytest.raises(DailyPriceRevisionWriteError, match='已核驗排除'):
        prepare_daily_price_revision_frame(database,closed)


def _hash_payload(payload: dict[str, object]) -> str:
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _row(symbol: str, close: str, *, sign: str = "+") -> dict[str, str]:
    return {
        "日期": "20260520",
        "證券代號": symbol,
        "證券名稱": f"測試股票{symbol}",
        "成交股數": "1000",
        "成交筆數": "20",
        "成交金額": str(int(float(close) * 1000)),
        "開盤價": close,
        "最高價": close,
        "最低價": close,
        "收盤價": close,
        "漲跌(+/-)": sign,
        "漲跌": sign,
        "涨跌": sign,
        "漲跌價差": "1.0",
        "最後揭示買價": close,
        "最後揭示買量": "10",
        "最後揭示賣價": close,
        "最後揭示賣量": "10",
        "本益比": "0",
    }


def _write_receipt(database_path: Path, *, pending: bool = True) -> dict[str, object]:
    receipt_dir = database_path.resolve().parent.parent / REPAIR_RECEIPT_RELATIVE_DIR
    receipt_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for symbol, close in (("1256", "183"), ("1477", "213")):
        after = _row(symbol, close)
        before = _row(symbol, str(float(close) - 1))
        rows.append(
            {
                "date": "20260520",
                "symbol": symbol,
                "before": before,
                "after": after,
                "source": {**after, "date": "20260520", "symbol": symbol},
                "differing_fields": ["close", "open", "high", "low"],
            }
        )
    body: dict[str, object] = {
        "schema_version": REPAIR_SCHEMA,
        "receipt_kind": "historical_price_spike_repair",
        "status": "applied",
        "source_date": "20260520",
        "source_update_columns": UPDATE_COLUMNS,
        "allowlist_count": len(rows),
        "allowlist_hash": "sha256:" + "a" * 64,
        "plan_hash": "sha256:" + "b" * 64,
        "canonical_sha256": "sha256:" + "c" * 64,
        "db_path": str(database_path.resolve()),
        "rows": rows,
    }
    receipt = {**body, "receipt_sha256": _hash_payload(body)}
    (receipt_dir / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    if pending:
        pending_payload = {
            "schema_version": REPAIR_SCHEMA,
            "receipt_kind": "historical_price_spike_repair_pending",
            "status": "applied_receipt_written",
            "source_date": body["source_date"],
            "allowlist_count": body["allowlist_count"],
            "allowlist_hash": body["allowlist_hash"],
            "plan_hash": body["plan_hash"],
            "canonical_sha256": body["canonical_sha256"],
            "db_path": body["db_path"],
        }
        (receipt_dir / "pending.json").write_text(
            json.dumps(pending_payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
    return receipt


def _database_path(tmp_path: Path) -> Path:
    sqlite_dir = tmp_path / "sqlite"
    sqlite_dir.mkdir(parents=True, exist_ok=True)
    return sqlite_dir / "twstock.db"


def _db_manager(tmp_path: Path):
    from data_module.db_manager import DBManager

    database_path = _database_path(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return DBManager(SimpleNamespace(db_file=database_path, log_dir=log_dir))


@pytest.mark.parametrize('writer', ['manager', 'upsert', 'date_replace', 'table_replace'])
def test_technical_writers_reject_verified_exclusions_before_mutating(tmp_path, monkeypatch, writer):
    from data_module import excluded_daily_price_revision
    monkeypatch.setattr(excluded_daily_price_revision, 'load_exclusion_evidence', lambda _: [{'keys': [], 'closed_dates': ['20241002']}])
    manager = _db_manager(tmp_path)
    frame = pd.DataFrame({'日期':['20241002'],'證券代號':['9999'],'new_column':[99]})
    before_columns = manager.get_table_columns('technical_indicators')
    service = UpdateService.__new__(UpdateService)
    if writer == 'manager':
        assert not manager.write_dataframe('technical_indicators',frame)
    elif writer == 'upsert':
        assert not service._upsert_sqlite_rows(manager,'technical_indicators',frame)
    else:
        with pytest.raises(DailyPriceRevisionWriteError, match='已核驗排除'):
            method = service._replace_sqlite_dates if writer=='date_replace' else service._replace_sqlite_table
            method(manager,'technical_indicators',frame)
    assert manager.get_table_columns('technical_indicators')==before_columns
    with manager.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM technical_indicators').fetchone()[0]==0


def _write_session_revision(database_path: Path) -> list[dict[str, object]]:
    root = database_path.resolve().parent.parent
    directory = root / SESSION_RECEIPT_DIR / "run01"
    directory.mkdir(parents=True)
    rows: list[dict[str, object]] = []
    for symbol, close in (("1256", 103), ("5001", 20)):
        rows.append(
            {
                "日期": "20141227",
                "證券代號": symbol,
                "證券名稱": f"測試股票{symbol}",
                "成交股數": 1000,
                "成交筆數": 10,
                "成交金額": 100000,
                "開盤價": close,
                "最高價": close + 2,
                "最低價": close - 2,
                "收盤價": close,
                "漲跌": "+",
                "漲跌價差": 1,
                "最後揭示買價": close - 1,
                "最後揭示買量": 10,
                "最後揭示賣價": close,
                "最後揭示賣量": 10,
                "本益比": 0,
            }
        )
    plan = {
        "schema_version": "historical-session-repair.v1",
        "database_path": str(database_path.resolve()),
        "dates": ["20141227"],
        "source_start_date": "2014-12-27",
        "source_end_date": "2014-12-27",
        "rows": rows,
    }
    plan_bytes = (
        json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    (directory / "plan.json").write_bytes(plan_bytes)
    plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()
    receipt_bytes = (
        json.dumps(
            {
                "schema_version": "historical-session-repair.v1",
                "state": "applied",
                "plan_sha256": plan_sha256,
                "dates": plan["dates"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    (directory / "receipt.json").write_bytes(receipt_bytes)
    marker = {
        "schema_version": "historical-session-revision.v1",
        "database_path": str(database_path.resolve()),
        "historical_pit": False,
        "plan_sha256": plan_sha256,
        "state": "applied",
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
    }
    (directory / "revision.json").write_text(
        json.dumps(marker, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return rows


def test_real_receipt_shape_accepts_canonical_rows_and_unmodified_keys(tmp_path: Path) -> None:
    database_path = _database_path(tmp_path)
    _write_receipt(database_path)
    frame = pd.DataFrame(
        [
            {"日期": "2026-05-20", "證券代號": "1256", "收盤價": 183.0},
            {"日期": "20260520", "證券代號": "1477", "收盤價": "213.00"},
            {"日期": "20260520", "證券代號": "2330", "收盤價": 1200},
        ]
    )

    prepared = prepare_daily_price_revision_frame(database_path, frame)

    pd.testing.assert_frame_equal(prepared, frame)


def test_stale_row_is_rejected_and_full_replacement_requires_all_keys(tmp_path: Path) -> None:
    database_path = _database_path(tmp_path)
    _write_receipt(database_path)
    stale = pd.DataFrame(
        [{"日期": "20260520", "證券代號": "1256", "收盤價": 182.0}]
    )

    with pytest.raises(DailyPriceRevisionWriteError, match="舊來源會覆蓋"):
        prepare_daily_price_revision_frame(database_path, stale)

    full = pd.DataFrame(
        [
            {**_row("1256", "183"), "證券代號": "1256"},
            {**_row("1477", "213"), "證券代號": "1477"},
        ]
    )
    incomplete = full.iloc[:1]
    with pytest.raises(DailyPriceRevisionWriteError, match="缺少已修訂 key"):
        prepare_daily_price_revision_frame(database_path, incomplete, replace_all=True)
    with pytest.raises(DailyPriceRevisionWriteError, match="缺少已修訂 key"):
        prepare_daily_price_revision_frame(
            database_path,
            incomplete,
            replace_dates=["2026-05-20"],
        )
    assert len(
        prepare_daily_price_revision_frame(
            database_path,
            full,
            replace_dates=["20260520"],
        )
    ) == 2

    missing_field = full.drop(columns=["成交股數"])
    with pytest.raises(DailyPriceRevisionWriteError, match="缺少修訂欄位"):
        prepare_daily_price_revision_frame(database_path, missing_field, replace_all=True)


def test_corrupt_receipt_fails_closed_for_unmodified_source_key(tmp_path: Path) -> None:
    database_path = _database_path(tmp_path)
    _write_receipt(database_path)
    receipt_path = (
        database_path.resolve().parent.parent
        / REPAIR_RECEIPT_RELATIVE_DIR
        / "receipt.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["rows"][0]["after"]["收盤價"] = "999"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(DailyPriceRevisionWriteError, match="hash mismatch"):
        DailyPriceRevisionWriteGuard(database_path).prepare_frame(
            pd.DataFrame([{"日期": "20260520", "證券代號": "2330", "收盤價": 1200}])
        )


def test_db_manager_rejects_before_schema_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = _database_path(tmp_path)
    _write_receipt(database_path)
    from data_module.db_manager import DBManager

    manager = DBManager.__new__(DBManager)
    manager.db_path = database_path
    manager.logger = logging.getLogger("test_daily_price_revision_write_guard")
    ensured: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        manager,
        "ensure_columns",
        lambda table, columns: ensured.append((table, columns)),
    )

    success = manager.write_dataframe(
        "daily_prices",
        pd.DataFrame([{"日期": "20260520", "證券代號": "1256", "收盤價": 182}]),
        if_exists="replace",
    )

    assert success is False
    assert ensured == []


@pytest.mark.parametrize("writer", ["upsert", "date_replace"])
def test_update_service_rejects_stale_daily_source_before_mutation(
    tmp_path: Path, writer: str
) -> None:
    database_path = _database_path(tmp_path)
    _write_receipt(database_path)
    service = UpdateService.__new__(UpdateService)

    class FakeDB:
        db_path = database_path

        def __init__(self) -> None:
            self.ensure_called = False

        def ensure_columns(self, *args, **kwargs):
            self.ensure_called = True

        def connect(self):
            raise AssertionError("stale source must fail before DELETE/INSERT")

    db = FakeDB()
    stale = pd.DataFrame(
        [
            {**_row("1256", "183"), "證券代號": "1256", "收盤價": "182"},
            {**_row("1477", "213"), "證券代號": "1477"},
        ]
    )
    if writer == "upsert":
        result = service._upsert_sqlite_rows(db, "daily_prices", stale)
        assert result is False
    else:
        with pytest.raises(DailyPriceRevisionWriteError, match="舊來源會覆蓋"):
            service._replace_sqlite_dates(db, "daily_prices", stale)
    assert db.ensure_called is False


def test_migration_rejects_stale_source_before_daily_prices_delete(tmp_path: Path) -> None:
    database_path = _database_path(tmp_path)
    _write_receipt(database_path)
    source = tmp_path / "all_stocks_data.csv"
    pd.DataFrame(
        [
            {"日期": "20260520", "證券代號": "1256", "收盤價": 182},
            {"日期": "20260520", "證券代號": "1477", "收盤價": 213},
        ]
    ).to_csv(source, index=False, encoding="utf-8-sig")
    config = SimpleNamespace(
        all_stocks_data_file=source,
        stock_data_file=tmp_path / "stock_data_whole.csv",
    )

    class FakeDB:
        db_path = database_path

        def __init__(self) -> None:
            self.delete_attempted = False
            self.writes = 0

        def connect(self):
            self.delete_attempted = True
            raise AssertionError("stale source must be rejected before DELETE")

        def write_dataframe(self, *args, **kwargs):
            self.writes += 1
            return True

    db = FakeDB()
    migrate_csv_to_sqlite.migrate_daily_prices(
        config, db, logging.getLogger("test_migrate_csv_to_sqlite")
    )

    assert not db.delete_attempted
    assert db.writes == 0


def test_shared_guard_checks_applied_historical_session_plan(tmp_path: Path) -> None:
    database_path = _database_path(tmp_path)
    plan_rows = _write_session_revision(database_path)
    incomplete = pd.DataFrame([plan_rows[0]])
    complete = pd.DataFrame(plan_rows)

    with pytest.raises(ValueError, match="缺少"):
        prepare_daily_price_revision_frame(
            database_path,
            incomplete,
            replace_dates=["20141227"],
        )
    prepared = prepare_daily_price_revision_frame(
        database_path,
        complete,
        replace_dates=["20141227"],
    )
    assert len(prepared) == 2


def test_migration_rejects_incomplete_session_date_before_delete(tmp_path: Path) -> None:
    database_path = _database_path(tmp_path)
    session_rows = _write_session_revision(database_path)
    source = tmp_path / "all_stocks_data.csv"
    pd.DataFrame([session_rows[0]]).to_csv(
        source, index=False, encoding="utf-8-sig"
    )
    config = SimpleNamespace(
        all_stocks_data_file=source,
        stock_data_file=tmp_path / "stock_data_whole.csv",
    )

    class FakeDB:
        db_path = database_path

        def __init__(self) -> None:
            self.delete_attempted = False
            self.writes = 0

        def connect(self):
            self.delete_attempted = True
            raise AssertionError("incomplete session source must fail before DELETE")

        def write_dataframe(self, *args, **kwargs):
            self.writes += 1
            return True

    db = FakeDB()
    migrate_csv_to_sqlite.migrate_daily_prices(
        config, db, logging.getLogger("test_migrate_session_revision")
    )

    assert not db.delete_attempted
    assert db.writes == 0


def test_market_migration_keeps_ohlcv_and_does_not_invent_zeroes(tmp_path: Path) -> None:
    market_file = tmp_path / "market_index.csv"
    pd.DataFrame(
        [
            {
                "日期": "2026-05-20",
                "指數名稱": "加權指數",
                "開盤價": 21000,
                "最高價": 21100,
                "最低價": 20900,
                "收盤價": 21050,
                "成交量": 100000000,
                "來源額外欄位": "保留",
            }
        ]
    ).to_csv(market_file, index=False, encoding="utf-8-sig")
    config = SimpleNamespace(
        market_index_file=market_file,
        industry_index_file=tmp_path / "missing_industry.csv",
    )

    class FakeDB:
        def __init__(self) -> None:
            self.writes: list[tuple[str, pd.DataFrame, str]] = []

        def write_dataframe(self, table: str, frame: pd.DataFrame, if_exists: str) -> bool:
            self.writes.append((table, frame.copy(), if_exists))
            return True

    db = FakeDB()
    migrate_csv_to_sqlite.migrate_market_and_industry_indices(
        config, db, logging.getLogger("test_market_csv_migration")
    )

    assert len(db.writes) == 1
    table, frame, if_exists = db.writes[0]
    assert table == "market_indices"
    assert if_exists == "replace"
    assert frame.loc[0, "指數名稱"] == "TAIEX"
    assert frame.loc[0, "開盤價"] == 21000
    assert frame.loc[0, "最高價"] == 21100
    assert frame.loc[0, "最低價"] == 20900
    assert frame.loc[0, "收盤價"] == 21050
    assert frame.loc[0, "成交量"] == 100000000
    assert frame.loc[0, "來源額外欄位"] == "保留"
    assert "漲跌點數" not in frame.columns
    assert "漲跌百分比" not in frame.columns


def test_db_manager_protected_replace_preserves_existing_keys_and_columns(tmp_path: Path) -> None:
    database_path = _database_path(tmp_path)
    _write_receipt(database_path)
    manager = _db_manager(tmp_path)
    with manager.connect() as conn:
        conn.execute('ALTER TABLE daily_prices ADD COLUMN "extra" TEXT;')
        conn.execute(
            'INSERT INTO daily_prices ("日期", "證券代號", "收盤價", "extra") '
            "VALUES ('20260519', '2330', 1000, 'keep-schema')"
        )

    source = pd.DataFrame(
        [
            {**_row("1256", "183"), "證券代號": "1256"},
            {**_row("1477", "213"), "證券代號": "1477"},
        ]
    )
    assert manager.write_dataframe("daily_prices", source, if_exists="replace")

    with manager.connect() as conn:
        columns = {row[1]: row[5] for row in conn.execute('PRAGMA table_info("daily_prices")')}
        rows = conn.execute(
            'SELECT "日期", "證券代號", "收盤價", "extra" FROM daily_prices ORDER BY "證券代號"'
        ).fetchall()
        primary_key_columns = {
            row[1]
            for row in conn.execute('PRAGMA table_info("daily_prices")')
            if row[5]
        }
    assert columns["extra"] == 0
    assert primary_key_columns == {"日期", "證券代號"}
    assert [tuple(row[:3]) for row in rows] == [
        ("20260520", "1256", 183),
        ("20260520", "1477", 213),
    ]


def test_market_manager_replace_preserves_existing_schema(tmp_path: Path) -> None:
    manager = _db_manager(tmp_path)
    with manager.connect() as conn:
        conn.execute('ALTER TABLE market_indices ADD COLUMN "extra" TEXT;')
        conn.execute(
            'INSERT INTO market_indices ("日期", "指數名稱", "收盤指數", "extra") '
            "VALUES ('20260519', 'TAIEX', 21000, 'keep-schema')"
        )
    source = pd.DataFrame(
        [
            {
                "日期": "20260520",
                "指數名稱": "TAIEX",
                "收盤指數": 21100,
                "開盤價": 21000,
                "最高價": 21200,
                "最低價": 20900,
                "收盤價": 21100,
                "成交量": 100000000,
            }
        ]
    )

    assert manager.write_dataframe("market_indices", source, if_exists="replace")
    with manager.connect() as conn:
        schema = conn.execute('PRAGMA table_info("market_indices")').fetchall()
        rows = conn.execute('SELECT "日期", "指數名稱", "extra" FROM market_indices').fetchall()
    assert {row[1] for row in schema if row[5]} == {"日期", "指數名稱"}
    assert "extra" in {row[1] for row in schema}
    assert [tuple(row) for row in rows] == [("20260520", "TAIEX", None)]


def test_db_manager_protected_replace_failure_rolls_back(tmp_path: Path, monkeypatch) -> None:
    database_path = _database_path(tmp_path)
    _write_receipt(database_path)
    manager = _db_manager(tmp_path)
    with manager.connect() as conn:
        conn.execute(
            'INSERT INTO daily_prices ("日期", "證券代號", "收盤價") '
            "VALUES ('20100101', '2330', 500)"
        )
    source = pd.DataFrame(
        [
            {**_row("1256", "183"), "證券代號": "1256"},
            {**_row("1477", "213"), "證券代號": "1477"},
        ]
    )

    def fail_insert(*args, **kwargs) -> None:
        raise sqlite3.OperationalError("injected insert failure")

    monkeypatch.setattr(manager, "_insert_dataframe_rows", fail_insert)
    assert manager.write_dataframe("daily_prices", source, if_exists="replace") is False

    with manager.connect() as conn:
        rows = conn.execute(
            'SELECT "日期", "證券代號", "收盤價" FROM daily_prices'
        ).fetchall()
    assert [tuple(row) for row in rows] == [("20100101", "2330", 500)]


def test_market_update_sync_normalizes_legacy_taiex_name(tmp_path: Path) -> None:
    market_file = tmp_path / "market_index.csv"
    pd.DataFrame(
        [
            {
                "日期": "20260520",
                "指數名稱": "加權指數",
                "開盤價": 21000,
                "最高價": 21200,
                "最低價": 20900,
                "收盤價": 21100,
                "成交量": 100000000,
            }
        ]
    ).to_csv(market_file, index=False, encoding="utf-8-sig")
    database_path = _database_path(tmp_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    service = UpdateService.__new__(UpdateService)
    service.config = SimpleNamespace(
        use_sqlite=True,
        profile="test",
        market_index_file=market_file,
        db_file=database_path,
        log_dir=log_dir,
    )

    result = service.sync_source_to_sqlite("market_index")

    assert result["success"] is True
    with sqlite3.connect(database_path) as conn:
        rows = conn.execute(
            'SELECT "指數名稱", "開盤價", "最高價", "最低價", "收盤價", "成交量" '
            'FROM market_indices WHERE "日期"="20260520"'
        ).fetchall()
    assert rows == [("TAIEX", 21000, 21200, 20900, 21100, 100000000)]


def test_migration_second_chunk_failure_rolls_back_full_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = _database_path(tmp_path)
    _write_receipt(database_path)
    manager = _db_manager(tmp_path)
    with manager.connect() as conn:
        conn.execute(
            'INSERT INTO daily_prices ("日期", "證券代號", "收盤價") '
            "VALUES ('20100101', '2330', 500)"
        )

    source = tmp_path / "all_stocks_data.csv"
    pd.DataFrame(
        [
            {"日期": "20260520", "證券代號": "1256", "收盤價": 183},
            {"日期": "20260520", "證券代號": "1477", "收盤價": 213},
            {"日期": "20260520", "證券代號": "2330", "收盤價": 1200},
        ]
    ).to_csv(source, index=False, encoding="utf-8-sig")
    config = SimpleNamespace(
        all_stocks_data_file=source,
        stock_data_file=tmp_path / "stock_data_whole.csv",
    )
    monkeypatch.setattr(migrate_csv_to_sqlite, "DAILY_MIGRATION_CHUNK_SIZE", 2)
    from data_module.db_manager import DBManager

    insert_rows = DBManager._insert_dataframe_rows
    calls = 0

    def fail_second_chunk(conn, table_name: str, frame: pd.DataFrame) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.OperationalError("injected second-chunk failure")
        insert_rows(conn, table_name, frame)

    monkeypatch.setattr(manager, "_insert_dataframe_rows", fail_second_chunk)
    migrate_csv_to_sqlite.migrate_daily_prices(
        config, manager, logging.getLogger("test_migration_transaction")
    )

    with manager.connect() as conn:
        old_rows = conn.execute(
            'SELECT "證券代號", "收盤價" FROM daily_prices WHERE "日期"="20100101"'
        ).fetchall()
        migrated_rows = conn.execute(
            'SELECT count(*) FROM daily_prices WHERE "日期"="20260520"'
        ).fetchone()[0]
    assert calls == 2
    assert [tuple(row) for row in old_rows] == [("2330", 500)]
    assert migrated_rows == 0
