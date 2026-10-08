"""Pinned SQLite read session 的合成檔案與唯讀交易測試。"""

from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import sqlite3
from typing import Callable, cast

import pytest

import data_module.pinned_sqlite_read_session as pinned_reader
from data_module.pinned_sqlite_read_session import (
    PinnedSQLiteReadSession,
    PinnedSQLiteReadSessionCancelled,
    PinnedSQLiteReadSessionError,
)


def _create_database(path: Path, *, rows: int = 3, journal_mode: str = "DELETE") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        mode_row = connection.execute(f"PRAGMA journal_mode={journal_mode}").fetchone()
        assert mode_row is not None
        connection.execute("CREATE TABLE IF NOT EXISTS saved_values (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("DELETE FROM saved_values")
        connection.executemany(
            "INSERT INTO saved_values (key, value) VALUES (?, ?)",
            [(f"k{index}", f"v{index}") for index in range(rows)],
        )
        connection.commit()
    finally:
        connection.close()
    return _file_sha256(path)


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@pytest.fixture
def source_and_private_roots(tmp_path: Path) -> tuple[Path, Path, str]:
    source_dir = tmp_path / "source"
    private_root = tmp_path / "reader"
    source_dir.mkdir()
    private_root.mkdir()
    database = source_dir / "saved.sqlite"
    expected_sha = _create_database(database)
    return database, private_root, expected_sha


def _open(
    database: Path,
    private_root: Path,
    expected_sha: str,
    **kwargs: object,
) -> PinnedSQLiteReadSession:
    return PinnedSQLiteReadSession.open_copy(
        database,
        expected_main_sha256=expected_sha,
        private_root=private_root,
        max_copy_bytes=64 * 1024 * 1024,
        **kwargs,  # type: ignore[arg-type]
    )


def test_copy_session_uses_one_query_only_transaction_and_removes_its_copy(
    source_and_private_roots: tuple[Path, Path, str],
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    original_stat = database.stat()
    original_hash = _file_sha256(database)

    session = _open(database, private_root, expected_sha)
    connection = session.connection
    private_path = Path(session.reader_database_path)

    assert connection.execute("PRAGMA query_only").fetchone() == (1,)
    assert connection.in_transaction
    assert connection.execute("SELECT key, value FROM saved_values ORDER BY key").fetchall() == [
        ("k0", "v0"),
        ("k1", "v1"),
        ("k2", "v2"),
    ]
    assert {item.name for item in session.schema_objects} >= {"saved_values"}
    assert session.schema_sha256
    assert private_path.exists()
    assert session.source_file_group_start[0].sha256 == expected_sha
    assert session.source_file_group_start[0].ctime_ns is not None
    assert session.source_file_group_start[0].nlink == 1
    assert session.source_file_group_start[0].ancestors

    binding = session.finish()

    assert binding.reader_copy_lifecycle == "closed_and_removed"
    assert binding.source_file_group_start == binding.source_file_group_finish
    assert binding.reader_copy_sha256 == expected_sha
    assert binding.identity_sha256 == binding.to_dict()["identity_sha256"]
    assert not private_path.exists()
    assert list(private_root.iterdir()) == []
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    with pytest.raises(PinnedSQLiteReadSessionError, match="connection_unavailable"):
        _ = session.connection
    with pytest.raises(PinnedSQLiteReadSessionError, match="finish_not_active"):
        session.finish()
    assert _file_sha256(database) == original_hash
    assert database.stat().st_size == original_stat.st_size
    assert database.stat().st_mtime_ns == original_stat.st_mtime_ns


def test_sqlite_connection_never_targets_original_database(
    source_and_private_roots: tuple[Path, Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    real_connect = sqlite3.connect
    seen: list[str] = []

    def guarded_connect(database_value: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        target = str(database_value)
        seen.append(target)
        assert "pinned-sqlite-" in target
        assert str(database) not in target
        connector = cast(Callable[..., sqlite3.Connection], real_connect)
        return connector(database_value, *args, **kwargs)

    monkeypatch.setattr(pinned_reader.sqlite3, "connect", guarded_connect)
    session = _open(database, private_root, expected_sha)
    assert len(seen) == 1
    assert session.connection.execute("SELECT COUNT(*) FROM saved_values").fetchone() == (3,)
    session.finish()


def test_authorizer_rejects_dml_ddl_attach_detach_vacuum_and_write_pragma(
    source_and_private_roots: tuple[Path, Path, str],
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    session = _open(database, private_root, expected_sha)
    connection = session.connection

    for statement in (
        "UPDATE saved_values SET value = 'changed' WHERE key = 'k0'",
        "CREATE TABLE injected (value TEXT)",
        "ATTACH DATABASE ':memory:' AS other",
        "DETACH DATABASE other",
        "PRAGMA user_version=9",
        "PRAGMA query_only=OFF",
        "VACUUM INTO 'outside.sqlite'",
    ):
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute(statement)
    assert connection.execute("PRAGMA user_version").fetchone() == (0,)
    assert connection.execute("PRAGMA table_info(saved_values)").fetchall()
    session.finish()


def test_empty_wal_and_present_shm_are_pinned_but_not_copied(
    source_and_private_roots: tuple[Path, Path, str],
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    wal = Path(str(database) + "-wal")
    shm = Path(str(database) + "-shm")
    wal.write_bytes(b"")
    shm.write_bytes(b"synthetic-shm-observation")
    original_group = {
        str(path): (_file_sha256(path), path.stat().st_size, path.stat().st_mtime_ns)
        for path in (database, wal, shm)
    }

    session = _open(database, private_root, expected_sha)
    assert session.source_file_group_start[1].present
    assert session.source_file_group_start[1].size_bytes == 0
    assert session.source_file_group_start[2].present
    assert session.source_file_group_start[2].sha256 == _file_sha256(shm)
    private_path = Path(session.reader_database_path)
    assert not Path(str(private_path) + "-shm").exists()
    assert session.connection.execute("SELECT COUNT(*) FROM saved_values").fetchone() == (3,)
    session.finish()

    current_group = {
        str(path): (_file_sha256(path), path.stat().st_size, path.stat().st_mtime_ns)
        for path in (database, wal, shm)
    }
    assert current_group == original_group
    assert list(private_root.iterdir()) == []


def test_nonempty_wal_and_any_rollback_journal_fail_before_sqlite_open(
    source_and_private_roots: tuple[Path, Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    real_connect = sqlite3.connect

    def forbidden_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        raise AssertionError("拒絕來源 sidecar 前不可開 SQLite")

    monkeypatch.setattr(pinned_reader.sqlite3, "connect", forbidden_connect)
    wal = Path(str(database) + "-wal")
    wal.write_bytes(b"unbound-wal-frame")
    with pytest.raises(PinnedSQLiteReadSessionError, match="nonempty_wal_unsupported"):
        _open(database, private_root, expected_sha)
    wal.unlink()
    journal = Path(str(database) + "-journal")
    journal.write_bytes(b"")
    with pytest.raises(PinnedSQLiteReadSessionError, match="rollback_journal_unsupported"):
        _open(database, private_root, expected_sha)
    assert list(private_root.iterdir()) == []
    monkeypatch.setattr(pinned_reader.sqlite3, "connect", real_connect)


def test_source_change_after_copy_is_rejected_and_private_copy_is_removed(
    source_and_private_roots: tuple[Path, Path, str],
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    session = _open(database, private_root, expected_sha)
    raw = bytearray(database.read_bytes())
    raw[-1] ^= 1
    database.write_bytes(raw)

    with pytest.raises(PinnedSQLiteReadSessionError, match="source_changed"):
        session.finish()
    assert list(private_root.iterdir()) == []
    with pytest.raises(PinnedSQLiteReadSessionError, match="connection_unavailable"):
        _ = session.connection


def test_private_copy_byte_change_is_detected_before_binding_publication(
    source_and_private_roots: tuple[Path, Path, str],
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    session = _open(database, private_root, expected_sha)
    reader_path = Path(session.reader_database_path)
    changed = bytearray(reader_path.read_bytes())
    changed[-1] ^= 1
    reader_path.write_bytes(changed)

    with pytest.raises(PinnedSQLiteReadSessionError, match="reader_copy_changed"):
        session.finish()
    assert list(private_root.iterdir()) == []


def test_private_copy_replacement_is_rejected_and_unknown_files_are_preserved(
    source_and_private_roots: tuple[Path, Path, str],
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    session = _open(database, private_root, expected_sha)
    reader_path = Path(session.reader_database_path)
    replaced_path = reader_path.with_name("reader.sqlite.saved")
    try:
        reader_path.rename(replaced_path)
        reader_path.write_bytes(database.read_bytes())
    except OSError as exc:
        pytest.skip(f"此環境不允許改名開啟中的合成 SQLite 檔：{type(exc).__name__}")

    with pytest.raises(PinnedSQLiteReadSessionError, match="reader_copy_changed"):
        session.finish()
    assert replaced_path.exists()
    assert reader_path.exists()
    assert list(private_root.iterdir())


def test_private_copy_replacement_after_close_is_rejected_and_preserved(
    source_and_private_roots: tuple[Path, Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    session = _open(database, private_root, expected_sha)
    reader_path = Path(session.reader_database_path)
    replaced_path = reader_path.with_name("reader.sqlite.saved")
    original_close = session._close_connection

    def close_then_replace() -> None:
        original_close()
        reader_path.rename(replaced_path)
        reader_path.write_bytes(database.read_bytes())

    monkeypatch.setattr(session, "_close_connection", close_then_replace)
    with pytest.raises(PinnedSQLiteReadSessionError, match="reader_copy_changed"):
        session.finish()

    assert replaced_path.read_bytes() == database.read_bytes()
    assert reader_path.read_bytes() == database.read_bytes()
    assert {item.name for item in private_root.iterdir()} == {
        reader_path.parent.name
    }
    assert {item.name for item in reader_path.parent.iterdir()} == {
        "reader.sqlite",
        "reader.sqlite.saved",
    }


def test_schema_snapshot_has_hard_object_and_sql_bounds(
    source_and_private_roots: tuple[Path, Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    monkeypatch.setattr(pinned_reader, "MAX_SCHEMA_SQL_BYTES", 1)

    with pytest.raises(PinnedSQLiteReadSessionError, match="schema_sql_too_large"):
        _open(database, private_root, expected_sha)
    assert list(private_root.iterdir()) == []


def test_source_ancestor_replacement_is_rejected_at_finish(
    source_and_private_roots: tuple[Path, Path, str],
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    source_dir = database.parent
    session = _open(database, private_root, expected_sha)
    moved = source_dir.with_name(source_dir.name + "-moved")
    source_dir.rename(moved)
    source_dir.mkdir()

    with pytest.raises(PinnedSQLiteReadSessionError):
        session.finish()
    assert list(private_root.iterdir()) == []


def test_cancel_during_copy_aborts_and_cleans_only_its_directory(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    private_root = tmp_path / "reader"
    source_dir.mkdir()
    private_root.mkdir()
    database = source_dir / "large.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE blobs (value BLOB NOT NULL)")
        connection.execute("INSERT INTO blobs VALUES (zeroblob(?))", (5 * 1024 * 1024,))
        connection.commit()
    finally:
        connection.close()
    expected_sha = _file_sha256(database)
    copying = False

    def progress(stage: str, current: int, total: int) -> None:
        nonlocal copying
        del total
        if stage == "copy_snapshot_bytes" and current >= 1024 * 1024:
            copying = True

    def cancel() -> bool:
        return copying

    with pytest.raises(PinnedSQLiteReadSessionCancelled):
        _open(
            database,
            private_root,
            expected_sha,
            progress_callback=progress,
            cancel_callback=cancel,
        )
    assert list(private_root.iterdir()) == []


def test_callback_exceptions_fail_closed_without_creating_reader_copy(
    source_and_private_roots: tuple[Path, Path, str],
) -> None:
    database, private_root, expected_sha = source_and_private_roots

    def broken_cancel() -> bool:
        raise RuntimeError("synthetic callback failure")

    with pytest.raises(PinnedSQLiteReadSessionError, match="cancel_callback_failed"):
        _open(database, private_root, expected_sha, cancel_callback=broken_cancel)

    def broken_progress(stage: str, current: int, total: int) -> None:
        del current, total
        if stage == "pin_source_file_group":
            raise RuntimeError("synthetic progress failure")

    with pytest.raises(PinnedSQLiteReadSessionError, match="progress_callback_failed"):
        _open(database, private_root, expected_sha, progress_callback=broken_progress)
    assert list(private_root.iterdir()) == []


def test_cancel_before_finish_closes_connection_and_removes_copy(
    source_and_private_roots: tuple[Path, Path, str],
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    cancelled = False

    def cancel() -> bool:
        return cancelled

    session = _open(database, private_root, expected_sha, cancel_callback=cancel)
    connection = session.connection
    cancelled = True

    with pytest.raises(PinnedSQLiteReadSessionCancelled):
        session.finish()
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    assert list(private_root.iterdir()) == []


def test_copy_cap_and_explicit_root_checks_happen_before_temp_creation(
    source_and_private_roots: tuple[Path, Path, str],
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    with pytest.raises(PinnedSQLiteReadSessionError, match="copy_cap_exceeded"):
        PinnedSQLiteReadSession.open_copy(
            database,
            expected_main_sha256=expected_sha,
            private_root=private_root,
            max_copy_bytes=1,
        )
    with pytest.raises(PinnedSQLiteReadSessionError, match="private_root_not_canonical_absolute"):
        PinnedSQLiteReadSession.open_copy(
            database,
            expected_main_sha256=expected_sha,
            private_root=Path("relative-reader-root"),
            max_copy_bytes=1024,
        )
    overlapping = database.parent / "nested-reader"
    overlapping.mkdir()
    with pytest.raises(PinnedSQLiteReadSessionError, match="private_root_overlaps_source"):
        PinnedSQLiteReadSession.open_copy(
            database,
            expected_main_sha256=expected_sha,
            private_root=overlapping,
            max_copy_bytes=1024,
        )
    assert list(private_root.iterdir()) == []
    assert list(overlapping.iterdir()) == []


def test_hardlinked_source_is_rejected_before_copy(
    source_and_private_roots: tuple[Path, Path, str],
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    alias = database.with_name("alias.sqlite")
    try:
        os.link(database, alias)
    except OSError as exc:
        pytest.skip(f"此環境無法建立合成 hard link：{type(exc).__name__}")
    with pytest.raises(PinnedSQLiteReadSessionError, match="hardlink_rejected"):
        _open(database, private_root, expected_sha)
    alias.unlink()
    assert list(private_root.iterdir()) == []


def test_each_operation_creates_a_fresh_copy_and_rechecks_full_source(
    source_and_private_roots: tuple[Path, Path, str],
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    first = _open(database, private_root, expected_sha)
    first_path = Path(first.reader_database_path)
    first_binding = first.finish()
    second = _open(database, private_root, expected_sha)
    second_path = Path(second.reader_database_path)
    second_binding = second.finish()

    assert first_path != second_path
    assert first_binding.reader_copy_sha256 == second_binding.reader_copy_sha256 == expected_sha
    assert first_binding.identity_sha256 != second_binding.identity_sha256
    assert list(private_root.iterdir()) == []


def test_callback_return_must_be_exact_bool(source_and_private_roots: tuple[Path, Path, str]) -> None:
    database, private_root, expected_sha = source_and_private_roots
    with pytest.raises(PinnedSQLiteReadSessionError, match="cancel_callback_not_bool"):
        _open(database, private_root, expected_sha, cancel_callback=lambda: 0)  # type: ignore[arg-type]
    assert list(private_root.iterdir()) == []


def test_private_directory_permission_denied_fails_after_one_attempt(
    source_and_private_roots: tuple[Path, Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    before = database.stat()
    calls: list[Path] = []
    real_mkdir = os.mkdir

    def denied(path: object, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
        target = Path(os.fsdecode(cast(os.PathLike[str], path)))
        if target.parent == private_root:
            calls.append(target)
            raise PermissionError("合成私有根權限拒絕")
        real_mkdir(cast(str, path), mode, dir_fd=dir_fd)

    def forbidden_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        raise AssertionError("權限失敗前不得連 SQLite")

    monkeypatch.setattr(pinned_reader.os, "mkdir", denied)
    monkeypatch.setattr(pinned_reader.sqlite3, "connect", forbidden_connect)
    with pytest.raises(PinnedSQLiteReadSessionError, match="private_directory_create_failed"):
        _open(database, private_root, expected_sha)
    assert len(calls) == 1
    assert database.stat() == before
    assert _file_sha256(database) == expected_sha
    assert list(private_root.iterdir()) == []


def test_private_directory_collision_has_a_hard_limit_and_preserves_existing_files(
    source_and_private_roots: tuple[Path, Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    existing = private_root / ("pinned-sqlite-" + "a" * 32)
    existing.mkdir()
    sentinel = existing / "unrelated.txt"
    sentinel.write_bytes(b"preserve-existing")
    calls = 0
    real_mkdir = os.mkdir

    def counted(path: object, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
        nonlocal calls
        if Path(os.fsdecode(cast(os.PathLike[str], path))) == existing:
            calls += 1
        real_mkdir(cast(str, path), mode, dir_fd=dir_fd)

    monkeypatch.setattr(pinned_reader.secrets, "token_hex", lambda _size: "a" * 32)
    monkeypatch.setattr(pinned_reader.os, "mkdir", counted)
    with pytest.raises(PinnedSQLiteReadSessionError, match="private_directory_collision_limit"):
        _open(database, private_root, expected_sha)
    assert calls == pinned_reader.MAX_READER_DIRECTORY_ATTEMPTS == 32
    assert sentinel.read_bytes() == b"preserve-existing"
    assert list(private_root.iterdir()) == [existing]
    assert _file_sha256(database) == expected_sha


def test_private_directory_collision_can_be_cancelled_between_attempts(
    source_and_private_roots: tuple[Path, Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    cancelled = False
    calls = 0
    real_mkdir = os.mkdir

    def collision(path: object, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
        nonlocal cancelled, calls
        target = Path(os.fsdecode(cast(os.PathLike[str], path)))
        if target.parent == private_root:
            calls += 1
            cancelled = True
            raise FileExistsError("合成名稱碰撞")
        real_mkdir(cast(str, path), mode, dir_fd=dir_fd)

    monkeypatch.setattr(pinned_reader.os, "mkdir", collision)
    with pytest.raises(PinnedSQLiteReadSessionCancelled):
        _open(database, private_root, expected_sha, cancel_callback=lambda: cancelled)
    assert calls == 1
    assert list(private_root.iterdir()) == []
    assert _file_sha256(database) == expected_sha


def test_private_directory_collision_then_success_preserves_other_directory(
    source_and_private_roots: tuple[Path, Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, private_root, expected_sha = source_and_private_roots
    existing = private_root / ("pinned-sqlite-" + "a" * 32)
    existing.mkdir()
    sentinel = existing / "unrelated.txt"
    sentinel.write_bytes(b"preserve-existing")
    names = iter(("a" * 32, "b" * 32))
    monkeypatch.setattr(pinned_reader.secrets, "token_hex", lambda _size: next(names))
    session = _open(database, private_root, expected_sha)
    assert Path(session.reader_database_path).parent.name == "pinned-sqlite-" + "b" * 32
    assert session.connection.execute("SELECT COUNT(*) FROM saved_values").fetchone() == (3,)
    binding = session.finish()
    assert binding.original_main_sha256 == expected_sha
    assert binding.reader_copy_sha256 == expected_sha
    assert list(private_root.iterdir()) == [existing]
    assert sentinel.read_bytes() == b"preserve-existing"
