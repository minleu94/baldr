from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile


DEFAULT_KEEP_DATES = 5


def create_retained_backup(
    source_file: Path,
    backup_dir: Path,
    *,
    label: str | None = None,
    timestamp: str | None = None,
    keep_dates: int = DEFAULT_KEEP_DATES,
) -> Path | None:
    source_file = Path(source_file)
    if not source_file.exists():
        return None

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = _backup_prefix(source_file, label)
    backup_file = backup_dir / f"{prefix}_{timestamp}{source_file.suffix}"
    _copy_file_atomically(source_file, backup_file)
    cleanup_backup_series(backup_dir, prefix=prefix, keep_dates=keep_dates)
    return backup_file


def create_sqlite_retained_backup(
    source_file: Path,
    backup_dir: Path,
    *,
    label: str | None = None,
    timestamp: str | None = None,
    keep_dates: int = DEFAULT_KEEP_DATES,
) -> Path | None:
    """Create a consistent SQLite backup, including WAL pages.

    A database file copied with ``shutil.copy2`` can be missing committed WAL
    pages while another connection is open.  SQLite's online backup API reads
    the consistent database image instead.  The destination is built in the
    backup directory and atomically renamed only after ``quick_check`` passes.
    """

    source_file = Path(source_file)
    if not source_file.exists():
        return None

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = _backup_prefix(source_file, label)
    backup_file = backup_dir / f"{prefix}_{timestamp}{source_file.suffix}"
    temporary_file: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{backup_file.stem}.",
            suffix=backup_file.suffix,
            dir=backup_dir,
            delete=False,
        ) as stream:
            temporary_file = Path(stream.name)
        source_connection = sqlite3.connect(source_file)
        destination_connection = sqlite3.connect(temporary_file)
        try:
            source_connection.backup(destination_connection)
            check = destination_connection.execute("PRAGMA quick_check").fetchone()
            if not check or str(check[0]).lower() != "ok":
                raise sqlite3.DatabaseError(
                    f"SQLite backup quick_check failed: {check!r}"
                )
            destination_connection.commit()
        finally:
            destination_connection.close()
            source_connection.close()
        temporary_file.replace(backup_file)
        temporary_file = None
        cleanup_backup_series(backup_dir, prefix=prefix, keep_dates=keep_dates)
        return backup_file
    finally:
        if temporary_file is not None:
            _unlink_if_exists(temporary_file)


def restore_sqlite_backup(backup_file: Path, destination_file: Path) -> None:
    """以 SQLite online backup 還原，確保 WAL 中已提交資料也被讀到。

    目的檔可能仍被 read-only consumer 開啟；直接 ``copy2`` 在 Windows
    會失敗，也可能遺漏 WAL。online backup 會在資料庫引擎內完成一致性
    複製，完成後再以 ``quick_check`` 驗證目的檔。
    """

    backup_file = Path(backup_file)
    destination_file = Path(destination_file)
    if not backup_file.exists():
        raise FileNotFoundError(backup_file)
    destination_file.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(backup_file)
    destination_connection = sqlite3.connect(destination_file)
    try:
        source_connection.backup(destination_connection)
        check = destination_connection.execute("PRAGMA quick_check").fetchone()
        if not check or str(check[0]).lower() != "ok":
            raise sqlite3.DatabaseError(
                f"SQLite restore quick_check failed: {check!r}"
            )
        destination_connection.commit()
    finally:
        destination_connection.close()
        source_connection.close()


def cleanup_backup_series(backup_dir: Path, *, prefix: str, keep_dates: int = DEFAULT_KEEP_DATES) -> None:
    if keep_dates < 1:
        keep_dates = 1

    backups_by_date: dict[str, list[Path]] = {}
    for backup_file in Path(backup_dir).glob(f"{prefix}_*"):
        if not backup_file.is_file():
            continue
        date_key, _ = _backup_sort_key(backup_file, prefix)
        if not date_key:
            continue
        backups_by_date.setdefault(date_key, []).append(backup_file)

    for backup_files in backups_by_date.values():
        sorted_files = sorted(
            backup_files,
            key=lambda path: (_backup_sort_key(path, prefix), path.stat().st_mtime),
            reverse=True,
        )
        for backup_file in sorted_files[1:]:
            _unlink_if_exists(backup_file)

    keep_date_keys = sorted(backups_by_date.keys(), reverse=True)[:keep_dates]
    for date_key, backup_files in backups_by_date.items():
        if date_key in keep_date_keys:
            continue
        for backup_file in backup_files:
            _unlink_if_exists(backup_file)


def _backup_prefix(source_file: Path, label: str | None) -> str:
    if not label:
        return source_file.stem
    return f"{source_file.stem}_{label}"


def _backup_sort_key(backup_file: Path, prefix: str) -> tuple[str, str]:
    pattern = rf"^{re.escape(prefix)}_(?P<date>\d{{8}})(?:_(?P<time>\d{{6}}))?$"
    match = re.match(pattern, backup_file.stem)
    if not match:
        return ("", "")
    return (match.group("date"), match.group("time") or "")


def _unlink_if_exists(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        return


def _copy_file_atomically(source_file: Path, destination_file: Path) -> None:
    """Copy one non-SQLite artifact without exposing a partial destination."""

    temporary_file: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination_file.stem}.",
            suffix=destination_file.suffix,
            dir=destination_file.parent,
            delete=False,
        ) as stream:
            temporary_file = Path(stream.name)
        shutil.copy2(source_file, temporary_file)
        temporary_file.replace(destination_file)
        temporary_file = None
    finally:
        if temporary_file is not None:
            _unlink_if_exists(temporary_file)
