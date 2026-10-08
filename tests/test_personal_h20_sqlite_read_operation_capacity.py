"""以隔離 SQLite 合成資料驗證 H20 operation 副本容量預留。"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sqlite3

import pytest

from scripts.scheduled.personal_h20_sqlite_read_operation import (
    DEFAULT_MAX_SOURCE_GROUPS,
    DEFAULT_MAX_TOTAL_COPY_BYTES,
    MAX_SOURCE_GROUPS_HARD_LIMIT,
    PersonalH20SQLiteReadOperation,
)


def _create_database(path: Path, value: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE saved_values (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO saved_values VALUES ('only', ?)", (value,))
    return sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    source_root = tmp_path / "source"
    private_root = tmp_path.parent / f"{tmp_path.name}-private-reader"
    source_root.mkdir()
    private_root.mkdir()
    return source_root, private_root


def test_defaults_are_bounded_and_capacity_arguments_reject_invalid_values(
    roots: tuple[Path, Path],
) -> None:
    _, private_root = roots
    operation = PersonalH20SQLiteReadOperation(private_root=private_root)
    assert operation.source_group_count == 0
    assert operation.copied_main_bytes == 0
    assert operation.reserved_copy_bytes == 0
    assert 1 <= DEFAULT_MAX_SOURCE_GROUPS <= MAX_SOURCE_GROUPS_HARD_LIMIT
    assert DEFAULT_MAX_TOTAL_COPY_BYTES > 0

    for kwargs in (
        {"max_source_groups": 0},
        {"max_source_groups": True},
        {"max_source_groups": MAX_SOURCE_GROUPS_HARD_LIMIT + 1},
        {"max_total_copy_bytes": 0},
        {"max_total_copy_bytes": True},
        {"max_total_copy_bytes": DEFAULT_MAX_TOTAL_COPY_BYTES + 1},
    ):
        with pytest.raises(ValueError):
            PersonalH20SQLiteReadOperation(private_root=private_root, **kwargs)


def test_exact_total_budget_counts_distinct_sources_once_and_allows_reuse(
    roots: tuple[Path, Path],
) -> None:
    source_root, private_root = roots
    first_path = source_root / "first.sqlite"
    second_path = source_root / "second.sqlite"
    first_sha = _create_database(first_path, "first")
    second_sha = _create_database(second_path, "second")
    expected_total = first_path.stat().st_size + second_path.stat().st_size

    with PersonalH20SQLiteReadOperation(
        private_root=private_root,
        max_source_groups=2,
        max_total_copy_bytes=expected_total,
    ) as operation:
        first = operation.session_for(first_path, first_sha)
        assert operation.copied_main_bytes == first_path.stat().st_size
        assert operation.reserved_copy_bytes == 0
        assert operation.source_group_count == 1
        assert operation.session_for(first_path, first_sha) is first
        assert operation.copied_main_bytes == first_path.stat().st_size

        operation.session_for(second_path, second_sha)
        assert operation.copied_main_bytes == expected_total
        assert operation.reserved_copy_bytes == 0
        assert operation.source_group_count == 2
        bindings = operation.finish()

    assert len(bindings) == 2
    assert not list(private_root.iterdir())


def test_total_budget_rejects_next_source_without_losing_existing_session(
    roots: tuple[Path, Path],
) -> None:
    source_root, private_root = roots
    first_path = source_root / "first.sqlite"
    second_path = source_root / "second.sqlite"
    first_sha = _create_database(first_path, "first")
    second_sha = _create_database(second_path, "second")

    with PersonalH20SQLiteReadOperation(
        private_root=private_root,
        max_total_copy_bytes=first_path.stat().st_size,
    ) as operation:
        first = operation.session_for(first_path, first_sha)
        with pytest.raises(ValueError, match="total_copy_budget_exceeded"):
            operation.session_for(second_path, second_sha)
        assert operation.source_group_count == 1
        assert operation.copied_main_bytes == first_path.stat().st_size
        assert operation.reserved_copy_bytes == 0
        assert first.connection.execute("SELECT value FROM saved_values").fetchone() == (
            "first",
        )
        assert len(operation.finish()) == 1

    assert not list(private_root.iterdir())


def test_source_group_limit_rejects_before_opening_another_copy(
    roots: tuple[Path, Path],
) -> None:
    source_root, private_root = roots
    first_path = source_root / "first.sqlite"
    second_path = source_root / "second.sqlite"
    first_sha = _create_database(first_path, "first")
    second_sha = _create_database(second_path, "second")

    with PersonalH20SQLiteReadOperation(
        private_root=private_root,
        max_source_groups=1,
        max_total_copy_bytes=first_path.stat().st_size + second_path.stat().st_size,
    ) as operation:
        operation.session_for(first_path, first_sha)
        with pytest.raises(ValueError, match="source_group_limit_exceeded"):
            operation.session_for(second_path, second_sha)
        assert operation.source_group_count == 1
        assert operation.copied_main_bytes == first_path.stat().st_size
        assert len(operation.finish()) == 1

    assert not list(private_root.iterdir())


def test_failed_source_hash_releases_reservation_and_next_verified_copy_succeeds(
    roots: tuple[Path, Path],
) -> None:
    source_root, private_root = roots
    database = source_root / "snapshot.sqlite"
    expected_sha = _create_database(database, "fixed")

    with PersonalH20SQLiteReadOperation(
        private_root=private_root,
        max_total_copy_bytes=database.stat().st_size,
    ) as operation:
        with pytest.raises(ValueError, match="main_sha_mismatch"):
            operation.session_for(database, "0" * 64)
        assert operation.source_group_count == 0
        assert operation.copied_main_bytes == 0
        assert operation.reserved_copy_bytes == 0
        assert not list(private_root.iterdir())

        operation.session_for(database, expected_sha)
        assert operation.source_group_count == 1
        assert operation.copied_main_bytes == database.stat().st_size
        assert operation.reserved_copy_bytes == 0
        assert len(operation.finish()) == 1

    assert not list(private_root.iterdir())


def test_cancel_after_reservation_releases_budget_before_any_copy(
    roots: tuple[Path, Path],
) -> None:
    source_root, private_root = roots
    database = source_root / "snapshot.sqlite"
    expected_sha = _create_database(database, "fixed")
    callback_count = 0

    def cancel_before_copy() -> bool:
        nonlocal callback_count
        callback_count += 1
        return callback_count == 2

    with PersonalH20SQLiteReadOperation(
        private_root=private_root,
        max_total_copy_bytes=database.stat().st_size,
        cancel_callback=cancel_before_copy,
    ) as operation:
        with pytest.raises(InterruptedError, match="cancelled"):
            operation.session_for(database, expected_sha)
        assert callback_count == 2
        assert operation.source_group_count == 0
        assert operation.copied_main_bytes == 0
        assert operation.reserved_copy_bytes == 0
        assert not list(private_root.iterdir())


def test_reentrant_copy_uses_reserved_size_and_rejects_source_growth(
    roots: tuple[Path, Path],
) -> None:
    source_root, private_root = roots
    first_path = source_root / "first.sqlite"
    second_path = source_root / "second.sqlite"
    first_sha = _create_database(first_path, "first")
    second_sha = _create_database(second_path, "second")
    first_size = first_path.stat().st_size
    second_size = second_path.stat().st_size
    nested_started = False

    operation: PersonalH20SQLiteReadOperation

    def progress(stage: str, _current: int, _total: int) -> None:
        nonlocal nested_started
        if stage == "pin_source_file_group" and not nested_started:
            nested_started = True
            # 重入的來源只能使用先扣除第一來源預留後的剩餘預算。
            operation.session_for(second_path, second_sha)
            with first_path.open("ab") as stream:
                stream.write(b"source grew after capacity reservation")

    operation = PersonalH20SQLiteReadOperation(
        private_root=private_root,
        max_source_groups=2,
        max_total_copy_bytes=first_size + second_size,
        progress_callback=progress,
    )
    with operation:
        with pytest.raises(ValueError, match="source_file_too_large|copy_cap_exceeded"):
            operation.session_for(first_path, first_sha)
        assert nested_started
        assert operation.source_group_count == 1
        assert operation.copied_main_bytes == second_size
        assert operation.reserved_copy_bytes == 0

    assert not list(private_root.iterdir())
