import sqlite3

from data_module.fundamental_migration import (
    apply_fundamental_schema_migration,
    restore_fundamental_schema_backup,
)
from data_module.backup_retention import (
    create_sqlite_retained_backup,
    restore_sqlite_backup,
)


def test_apply_fundamental_schema_migration_creates_backup_and_tables(tmp_path):
    db_file = tmp_path / "twstock.db"
    backup_dir = tmp_path / "backup"
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE daily_prices (id TEXT PRIMARY KEY)")

    result = apply_fundamental_schema_migration(db_file, backup_dir=backup_dir)

    assert result.applied is True
    assert result.backup_file is not None
    assert result.backup_file.exists()
    assert result.report.existing_tables_preserved is True
    with sqlite3.connect(db_file) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "fundamental_monthly_revenues" in tables
    assert "daily_prices" in tables


def test_restore_fundamental_schema_backup_restores_original_db(tmp_path):
    db_file = tmp_path / "twstock.db"
    backup_dir = tmp_path / "backup"
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE daily_prices (id TEXT PRIMARY KEY)")

    result = apply_fundamental_schema_migration(db_file, backup_dir=backup_dir)
    assert result.backup_file is not None

    restore_fundamental_schema_backup(result.backup_file, db_file)

    with sqlite3.connect(db_file) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"daily_prices"}


def test_apply_fundamental_schema_migration_rejects_missing_db(tmp_path):
    result = apply_fundamental_schema_migration(
        tmp_path / "missing.db",
        backup_dir=tmp_path / "backup",
    )

    assert result.applied is False
    assert result.backup_file is None
    assert result.diagnostics[0] == "source_db_missing"


def test_sqlite_retained_backup_includes_uncheckpointed_wal_pages(tmp_path):
    db_file = tmp_path / "wal.sqlite"
    backup_dir = tmp_path / "backup"
    connection = sqlite3.connect(db_file)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, value TEXT)")
        connection.executemany(
            "INSERT INTO observations(value) VALUES (?)",
            [("first",), ("second",)],
        )
        connection.commit()
        backup_file = create_sqlite_retained_backup(
            db_file,
            backup_dir,
            label="wal",
            timestamp="20260908_120000",
        )
    finally:
        connection.close()

    assert backup_file is not None
    with sqlite3.connect(backup_file) as backup:
        assert backup.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 2
        assert backup.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_restore_sqlite_backup_replaces_destination_contents_via_online_backup(tmp_path):
    source = tmp_path / "source.db"
    destination = tmp_path / "destination.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        conn.executemany(
            "INSERT INTO sample(value) VALUES (?)",
            [("before",), ("second",)],
        )
    with sqlite3.connect(destination) as conn:
        conn.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        conn.execute("INSERT INTO sample(value) VALUES ('after')")

    restore_sqlite_backup(source, destination)

    with sqlite3.connect(destination) as conn:
        assert conn.execute("SELECT value FROM sample ORDER BY rowid").fetchall() == [
            ("before",),
            ("second",),
        ]
