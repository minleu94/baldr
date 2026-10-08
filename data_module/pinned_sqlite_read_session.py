"""以原始檔案 pins 建立單次操作用的 SQLite 唯讀副本 session。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile
from typing import Callable, Literal


SQLiteFileRole = Literal["main", "wal", "shm", "rollback_journal", "reader_copy"]
SQLiteSidecarRole = Literal["wal", "shm", "rollback_journal"]

SQLITE_READ_SESSION_SCHEMA: Literal["pinned-sqlite-read-session.v1"] = (
    "pinned-sqlite-read-session.v1"
)
COPY_CHUNK_BYTES = 1024 * 1024
MAX_COPY_BYTES_HARD_LIMIT = 64 * 1024 * 1024 * 1024
MAX_SIDECAR_BYTES = 16 * 1024 * 1024
MAX_SHM_BYTES = 1024 * 1024
MAX_SOURCE_SIDECAR_TOTAL_BYTES = 32 * 1024 * 1024
MAX_SCHEMA_OBJECTS = 100_000
MAX_SCHEMA_SQL_BYTES = 256 * 1024
MAX_SCHEMA_TOTAL_BYTES = 16 * 1024 * 1024
MIN_READER_RESERVE_BYTES = 8 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_REPARSE_POINT = 0x400
_SOURCE_ROLES: tuple[SQLiteFileRole, ...] = ("main", "wal", "shm", "rollback_journal")
_READER_SIDE_SUFFIXES = ("-wal", "-shm", "-journal")
_READ_ONLY_PRAGMAS = frozenset(
    {
        "application_id",
        "collation_list",
        "compile_options",
        "database_list",
        "data_version",
        "integrity_check",
        "journal_mode",
        "quick_check",
        "query_only",
        "schema_version",
        "user_version",
    }
)
_READ_ONLY_PRAGMAS_WITH_ARGUMENT = frozenset(
    {
        "foreign_key_check",
        "foreign_key_list",
        "index_info",
        "index_list",
        "index_xinfo",
        "table_info",
        "table_list",
        "table_xinfo",
    }
)


class PinnedSQLiteReadSessionError(ValueError):
    """唯讀副本 session 無法滿足檔案、SQLite 或生命週期契約。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PinnedSQLiteReadSessionCancelled(InterruptedError):
    """建立或完成唯讀副本 session 時收到取消。"""

    def __init__(self) -> None:
        super().__init__("pinned_sqlite_read_cancelled")
        self.code = "pinned_sqlite_read_cancelled"


@dataclass(frozen=True, slots=True)
class SQLitePathIdentityV1:
    """路徑祖先的穩定實體身分；不含會受同層新增檔案影響的時間與連結數。"""

    path: str
    device: int
    inode: int
    mode: int
    file_attributes: int
    reparse: bool

    def __post_init__(self) -> None:
        if type(self.path) is not str or not Path(self.path).is_absolute():
            raise ValueError("祖先路徑必須是絕對路徑")
        for name in ("device", "inode", "mode", "file_attributes"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} 必須是非負整數")
        if self.inode == 0:
            raise ValueError("祖先路徑缺少可用 inode 身分")
        if type(self.reparse) is not bool or self.reparse:
            raise ValueError("祖先路徑不可為 reparse point")

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "device": self.device,
            "inode": self.inode,
            "mode": self.mode,
            "file_attributes": self.file_attributes,
            "reparse": self.reparse,
        }


@dataclass(frozen=True, slots=True)
class SQLiteFilePinV1:
    """SQLite 主檔或 sidecar 的完整 raw bytes、stat 與祖先身分 pin。"""

    role: SQLiteFileRole
    path: str
    present: bool
    device: int | None
    inode: int | None
    size_bytes: int | None
    mtime_ns: int | None
    ctime_ns: int | None
    mode: int | None
    nlink: int | None
    file_attributes: int | None
    reparse: bool
    sha256: str | None
    ancestors: tuple[SQLitePathIdentityV1, ...]

    def __post_init__(self) -> None:
        if self.role not in _SOURCE_ROLES and self.role != "reader_copy":
            raise ValueError("SQLite 檔案 pin role 不支援")
        if type(self.path) is not str or not Path(self.path).is_absolute():
            raise ValueError("SQLite 檔案 pin 路徑必須是絕對路徑")
        if type(self.present) is not bool or type(self.reparse) is not bool:
            raise TypeError("SQLite 檔案 pin 狀態必須是 bool")
        if type(self.ancestors) is not tuple or any(
            type(item) is not SQLitePathIdentityV1 for item in self.ancestors
        ):
            raise TypeError("SQLite 檔案 pin ancestors 型別錯誤")
        values = (
            self.device,
            self.inode,
            self.size_bytes,
            self.mtime_ns,
            self.ctime_ns,
            self.mode,
            self.nlink,
            self.file_attributes,
        )
        if self.present:
            if self.reparse:
                raise ValueError("已接受的 SQLite 檔案不可為 reparse point")
            if any(type(value) is not int or value < 0 for value in values):
                raise ValueError("存在檔案的 stat pin 必須是非負整數")
            if self.inode == 0 or self.nlink != 1:
                raise ValueError("SQLite 檔案必須有實體身分且僅有一個 hard link")
            if type(self.sha256) is not str or not _SHA256_RE.fullmatch(self.sha256):
                raise ValueError("存在檔案必須有小寫 SHA-256")
        elif any(value is not None for value in values) or self.sha256 is not None or self.reparse:
            raise ValueError("不存在檔案不可攜帶 stat、hash 或 reparse 狀態")

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(
            {
                "path": self.path,
                "ancestors": [item.to_dict() for item in self.ancestors],
                "device": self.device,
                "inode": self.inode,
                "mode": self.mode,
                "file_attributes": self.file_attributes,
                "reparse": self.reparse,
            }
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "path": self.path,
            "present": self.present,
            "device": self.device,
            "inode": self.inode,
            "size_bytes": self.size_bytes,
            "mtime_ns": self.mtime_ns,
            "ctime_ns": self.ctime_ns,
            "mode": self.mode,
            "nlink": self.nlink,
            "file_attributes": self.file_attributes,
            "reparse": self.reparse,
            "sha256": self.sha256,
            "ancestors": [item.to_dict() for item in self.ancestors],
            "identity_sha256": self.identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class SQLiteSchemaObjectV1:
    """固定 SQLite transaction view 讀到的 schema object。"""

    object_type: str
    name: str
    table_name: str
    sql: str | None

    def __post_init__(self) -> None:
        if any(type(value) is not str for value in (self.object_type, self.name, self.table_name)):
            raise TypeError("SQLite schema object 欄位必須是字串")
        if self.sql is not None and type(self.sql) is not str:
            raise TypeError("SQLite schema SQL 必須是字串或 None")

    def to_dict(self) -> dict[str, object]:
        return {
            "object_type": self.object_type,
            "name": self.name,
            "table_name": self.table_name,
            "sql": self.sql,
        }


@dataclass(frozen=True, slots=True)
class PinnedSQLiteReadBindingV1:
    """記錄原始 SQLite 檔案與已關閉私有 reader 副本的關係。"""

    original_database_path: str
    original_main_sha256: str
    reader_database_path: str
    reader_copy_sha256: str
    reader_copy_size_bytes: int
    source_file_group_start: tuple[SQLiteFilePinV1, ...]
    source_file_group_finish: tuple[SQLiteFilePinV1, ...]
    reader_copy_pin: SQLiteFilePinV1
    schema_objects: tuple[SQLiteSchemaObjectV1, ...]
    schema_sha256: str
    reader_journal_mode: str
    reader_copy_lifecycle: Literal["closed_and_removed"] = "closed_and_removed"
    transport: Literal["copy_main_empty_or_absent_wal"] = "copy_main_empty_or_absent_wal"
    schema_version: Literal["pinned-sqlite-read-session.v1"] = SQLITE_READ_SESSION_SCHEMA

    def __post_init__(self) -> None:
        for name in ("original_database_path", "reader_database_path"):
            value = getattr(self, name)
            if type(value) is not str or not Path(value).is_absolute():
                raise ValueError(f"{name} 必須是絕對路徑")
        for name in ("original_main_sha256", "reader_copy_sha256", "schema_sha256"):
            value = getattr(self, name)
            if type(value) is not str or not _SHA256_RE.fullmatch(value):
                raise ValueError(f"{name} 必須是小寫 SHA-256")
        if type(self.reader_copy_size_bytes) is not int or self.reader_copy_size_bytes < 0:
            raise ValueError("reader_copy_size_bytes 必須是非負整數")
        if self.schema_version != SQLITE_READ_SESSION_SCHEMA:
            raise ValueError("SQLite binding schema version 不支援")
        if self.reader_copy_lifecycle != "closed_and_removed":
            raise ValueError("reader copy 必須已關閉並移除")
        if self.transport != "copy_main_empty_or_absent_wal":
            raise ValueError("目前只支援 main-only copy")
        if type(self.source_file_group_start) is not tuple or type(
            self.source_file_group_finish
        ) is not tuple:
            raise TypeError("source file group pins 必須是 tuple")
        if tuple(pin.role for pin in self.source_file_group_start) != _SOURCE_ROLES:
            raise ValueError("source start pins 必須按固定順序包含四種檔案")
        if tuple(pin.role for pin in self.source_file_group_finish) != _SOURCE_ROLES:
            raise ValueError("source finish pins 必須按固定順序包含四種檔案")
        if self.source_file_group_start != self.source_file_group_finish:
            raise ValueError("來源 SQLite 檔案群組起訖 pins 不一致")
        if type(self.reader_copy_pin) is not SQLiteFilePinV1:
            raise TypeError("reader_copy_pin 型別錯誤")
        if self.reader_copy_pin.role != "reader_copy" or not self.reader_copy_pin.present:
            raise ValueError("reader_copy_pin 必須是存在的 reader copy")
        if self.reader_copy_pin.sha256 != self.reader_copy_sha256:
            raise ValueError("reader copy SHA 與 pin 不一致")
        if self.reader_copy_pin.size_bytes != self.reader_copy_size_bytes:
            raise ValueError("reader copy bytes 與 pin 不一致")
        if type(self.schema_objects) is not tuple or any(
            type(item) is not SQLiteSchemaObjectV1 for item in self.schema_objects
        ):
            raise TypeError("schema_objects 型別錯誤")
        if type(self.reader_journal_mode) is not str or not self.reader_journal_mode:
            raise ValueError("reader_journal_mode 不可為空")

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict(include_identity=False))

    def to_dict(self, *, include_identity: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "original_database_path": self.original_database_path,
            "original_main_sha256": self.original_main_sha256,
            "reader_database_path": self.reader_database_path,
            "reader_copy_sha256": self.reader_copy_sha256,
            "reader_copy_size_bytes": self.reader_copy_size_bytes,
            "source_file_group_start": [pin.to_dict() for pin in self.source_file_group_start],
            "source_file_group_finish": [pin.to_dict() for pin in self.source_file_group_finish],
            "reader_copy_pin": self.reader_copy_pin.to_dict(),
            "schema_objects": [item.to_dict() for item in self.schema_objects],
            "schema_sha256": self.schema_sha256,
            "reader_journal_mode": self.reader_journal_mode,
            "reader_copy_lifecycle": self.reader_copy_lifecycle,
            "transport": self.transport,
        }
        if include_identity:
            payload["identity_sha256"] = _canonical_sha256(payload)
        return payload


class PinnedSQLiteReadSession:
    """一條 transaction 共用一份私有 SQLite copy 的唯讀操作 session。"""

    def __init__(self) -> None:
        self._state: Literal["opening", "active", "finished", "closed", "failed"] = "opening"
        self._connection: sqlite3.Connection | None = None
        self._cancel_callback: Callable[[], bool] | None = None
        self._progress_callback: Callable[[str, int, int], None] | None = None
        self._source_path: Path | None = None
        self._private_root: Path | None = None
        self._private_root_chain: tuple[SQLitePathIdentityV1, ...] = ()
        self._reader_directory: Path | None = None
        self._reader_directory_identity: SQLitePathIdentityV1 | None = None
        self._reader_directory_chain_start: tuple[SQLitePathIdentityV1, ...] = ()
        self._reader_database_path: Path | None = None
        self._reader_copy_pin: SQLiteFilePinV1 | None = None
        self._reader_copy_creation_identity: tuple[int, int] | None = None
        self._source_start_pins: tuple[SQLiteFilePinV1, ...] = ()
        self._schema_objects: tuple[SQLiteSchemaObjectV1, ...] = ()
        self._schema_sha256: str | None = None
        self._reader_journal_mode: str | None = None
        self._internal_transaction_control = False
        self._owned_reader_sidecar_ids: dict[str, tuple[int, int]] = {}
        self._max_copy_bytes = 0

    @classmethod
    def open_copy(
        cls,
        source_database_path: Path | str,
        *,
        expected_main_sha256: str,
        private_root: Path | str,
        max_copy_bytes: int,
        cancel_callback: Callable[[], bool] | None = None,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> PinnedSQLiteReadSession:
        """核來源 pins、複製 main bytes，並在 copy 上建立唯讀 transaction。"""

        session = cls()
        try:
            session._open_copy(
                source_database_path,
                expected_main_sha256=expected_main_sha256,
                private_root=private_root,
                max_copy_bytes=max_copy_bytes,
                cancel_callback=cancel_callback,
                progress_callback=progress_callback,
            )
            return session
        except BaseException:
            session._state = "failed"
            session._close_connection_safely()
            session._cleanup_owned_copy(suppress_errors=True)
            raise

    @property
    def connection(self) -> sqlite3.Connection:
        """回傳本操作唯一的唯讀 SQLite connection。"""

        if self._state != "active" or self._connection is None:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_connection_unavailable")
        try:
            self._connection.execute("SELECT 1").fetchone()
        except sqlite3.Error as exc:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_connection_not_active") from exc
        return self._connection

    @property
    def schema_objects(self) -> tuple[SQLiteSchemaObjectV1, ...]:
        if self._state != "active":
            raise PinnedSQLiteReadSessionError("sqlite_read_session_schema_unavailable")
        return self._schema_objects

    @property
    def schema_sha256(self) -> str:
        if self._state != "active" or self._schema_sha256 is None:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_schema_unavailable")
        return self._schema_sha256

    @property
    def source_file_group_start(self) -> tuple[SQLiteFilePinV1, ...]:
        if self._state != "active":
            raise PinnedSQLiteReadSessionError("sqlite_read_session_pins_unavailable")
        return self._source_start_pins

    @property
    def reader_database_path(self) -> str:
        """僅供本次 session 診斷；finish 後該路徑已移除。"""

        if self._state != "active" or self._reader_database_path is None:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_path_unavailable")
        return str(self._reader_database_path)

    def finish(self) -> PinnedSQLiteReadBindingV1:
        """關閉 transaction，重核完整來源檔案群組，然後移除私有 copy。"""

        if self._state != "active":
            raise PinnedSQLiteReadSessionError("sqlite_read_session_finish_not_active")
        try:
            self._poll_cancel()
            self._record_reader_sidecars()
            self._close_connection()
            final_copy_pin = self._capture_reader_copy_pin()
            if final_copy_pin != self._reader_copy_pin:
                raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_copy_changed")
            self._report_progress("finish_source_revalidation", 0, 1)
            source_finish_pins = self._capture_source_file_group("finish_source_revalidation")
            if source_finish_pins != self._source_start_pins:
                raise PinnedSQLiteReadSessionError("sqlite_read_session_source_changed")
            if self._reader_copy_pin is None or self._reader_database_path is None:
                raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_pin_missing")
            if (
                self._schema_sha256 is None
                or self._reader_journal_mode is None
                or self._source_path is None
            ):
                raise PinnedSQLiteReadSessionError("sqlite_read_session_binding_incomplete")
            binding = PinnedSQLiteReadBindingV1(
                original_database_path=str(self._source_path),
                original_main_sha256=self._source_start_pins[0].sha256 or "",
                reader_database_path=str(self._reader_database_path),
                reader_copy_sha256=self._reader_copy_pin.sha256 or "",
                reader_copy_size_bytes=self._reader_copy_pin.size_bytes or 0,
                source_file_group_start=self._source_start_pins,
                source_file_group_finish=source_finish_pins,
                reader_copy_pin=self._reader_copy_pin,
                schema_objects=self._schema_objects,
                schema_sha256=self._schema_sha256,
                reader_journal_mode=self._reader_journal_mode,
            )
            self._cleanup_owned_copy(suppress_errors=False)
            self._state = "finished"
            return binding
        except BaseException:
            self._state = "failed"
            self._close_connection_safely()
            self._cleanup_owned_copy(suppress_errors=True)
            raise

    def close(self) -> None:
        """取消未完成 session，rollback/close 後只清除此 session 的 copy。"""

        if self._state == "active":
            self._state = "closed"
            try:
                self._record_reader_sidecars()
            except PinnedSQLiteReadSessionError:
                pass
            self._close_connection_safely()
            self._cleanup_owned_copy(suppress_errors=False)
            return
        if self._state in {"closed", "finished", "failed"}:
            return
        raise PinnedSQLiteReadSessionError("sqlite_read_session_close_not_active")

    def __enter__(self) -> PinnedSQLiteReadSession:
        if self._state != "active":
            raise PinnedSQLiteReadSessionError("sqlite_read_session_context_not_active")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._state == "active":
            self.close()

    def _open_copy(
        self,
        source_database_path: Path | str,
        *,
        expected_main_sha256: str,
        private_root: Path | str,
        max_copy_bytes: int,
        cancel_callback: Callable[[], bool] | None,
        progress_callback: Callable[[str, int, int], None] | None,
    ) -> None:
        if type(expected_main_sha256) is not str or not _SHA256_RE.fullmatch(
            expected_main_sha256
        ):
            raise PinnedSQLiteReadSessionError("sqlite_read_session_expected_sha_invalid")
        if type(max_copy_bytes) is not int or max_copy_bytes <= 0:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_cap_invalid")
        if max_copy_bytes > MAX_COPY_BYTES_HARD_LIMIT:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_cap_too_large")
        if cancel_callback is not None and not callable(cancel_callback):
            raise PinnedSQLiteReadSessionError("sqlite_read_session_cancel_callback_invalid")
        if progress_callback is not None and not callable(progress_callback):
            raise PinnedSQLiteReadSessionError("sqlite_read_session_progress_callback_invalid")
        source = _canonical_absolute_path(source_database_path, "source_database_path")
        private = _canonical_absolute_path(private_root, "private_root")
        self._source_path = source
        self._private_root = private
        self._cancel_callback = cancel_callback
        self._progress_callback = progress_callback
        self._max_copy_bytes = max_copy_bytes
        self._validate_private_root(private, source)
        _preflight_main_size(source, max_copy_bytes)
        self._poll_cancel()
        self._report_progress("pin_source_file_group", 0, 1)
        source_start = self._capture_source_file_group("pin_source_file_group")
        self._source_start_pins = source_start
        main_pin = source_start[0]
        if not main_pin.present or main_pin.sha256 != expected_main_sha256:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_main_sha_mismatch")
        main_size = main_pin.size_bytes
        if main_size is None or main_size > max_copy_bytes:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_cap_exceeded")
        wal_pin = source_start[1]
        if wal_pin.present and wal_pin.size_bytes != 0:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_nonempty_wal_unsupported")
        journal_pin = source_start[3]
        if journal_pin.present:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_rollback_journal_unsupported")
        if self._private_root_chain == ():
            raise PinnedSQLiteReadSessionError("sqlite_read_session_private_root_unpinned")
        free_bytes = shutil.disk_usage(private).free
        if free_bytes < main_size + MIN_READER_RESERVE_BYTES:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_private_capacity_insufficient")
        self._create_reader_directory()
        reader_dir = self._reader_directory
        if reader_dir is None:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_directory_missing")
        reader_path = reader_dir / "reader.sqlite"
        self._reader_database_path = reader_path
        self._report_progress("copy_snapshot_bytes", 0, main_size)
        copied_sha, copied_bytes, copy_stat = self._copy_source_main(main_pin, reader_path)
        if copied_sha != expected_main_sha256 or copied_sha != main_pin.sha256:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_sha_mismatch")
        if copied_bytes != main_size:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_size_mismatch")
        self._reader_copy_pin = self._pin_created_reader_copy(reader_path, copy_stat, copied_sha)
        self._poll_cancel()
        self._report_progress("open_private_reader", 0, 1)
        self._open_private_reader()
        self._state = "active"

    def _validate_private_root(self, private: Path, source: Path) -> None:
        if not private.is_absolute() or not source.is_absolute():
            raise PinnedSQLiteReadSessionError("sqlite_read_session_path_not_absolute")
        if _path_is_within(private, source.parent) or _path_is_within(source, private):
            raise PinnedSQLiteReadSessionError("sqlite_read_session_private_root_overlaps_source")
        self._private_root_chain = _directory_identity_chain(private, include_leaf=True)
        root_info = private.lstat()
        if not stat.S_ISDIR(root_info.st_mode) or _is_link_or_reparse(root_info):
            raise PinnedSQLiteReadSessionError("sqlite_read_session_private_root_not_plain_directory")

    def _create_reader_directory(self) -> None:
        private = self._private_root
        if private is None:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_private_root_missing")
        self._assert_private_root_unchanged()
        try:
            name = tempfile.mkdtemp(prefix="pinned-sqlite-", dir=str(private))
        except OSError as exc:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_private_directory_create_failed") from exc
        directory = Path(name)
        self._reader_directory = directory
        chain = _directory_identity_chain(directory, include_leaf=True)
        self._reader_directory_chain_start = chain
        self._reader_directory_identity = chain[-1]
        self._assert_private_root_unchanged()

    def _copy_source_main(
        self,
        expected_pin: SQLiteFilePinV1,
        reader_path: Path,
    ) -> tuple[str, int, os.stat_result]:
        source = self._source_path
        directory = self._reader_directory
        if source is None or directory is None:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_paths_missing")
        self._assert_source_ancestor_identity(expected_pin.ancestors)
        self._assert_reader_directory_identity()
        source_fd = _open_readonly_file(source, expected_pin)
        destination_fd: int | None = None
        digest = sha256()
        copied = 0
        try:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            destination_fd = os.open(str(reader_path), flags, 0o600)
            dest_before = os.fstat(destination_fd)
            if not stat.S_ISREG(dest_before.st_mode) or _is_link_or_reparse(dest_before):
                raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_not_regular")
            if getattr(dest_before, "st_nlink", None) != 1:
                raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_hardlink_rejected")
            self._reader_copy_creation_identity = _path_file_identity(dest_before)
            self._assert_reader_directory_identity()
            expected_size = expected_pin.size_bytes
            if expected_size is None:
                raise PinnedSQLiteReadSessionError("sqlite_read_session_main_size_missing")
            while True:
                self._poll_cancel()
                block = os.read(source_fd, COPY_CHUNK_BYTES)
                if not block:
                    break
                copied += len(block)
                if copied > self._max_copy_bytes or copied > expected_size:
                    raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_cap_exceeded")
                digest.update(block)
                view = memoryview(block)
                while view:
                    written = os.write(destination_fd, view)
                    if written <= 0:
                        raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_write_failed")
                    view = view[written:]
                self._report_progress("copy_snapshot_bytes", copied, expected_size)
            os.fsync(destination_fd)
            source_after = os.fstat(source_fd)
            if _file_stat_signature(source_after) != _pin_stat_signature(expected_pin):
                raise PinnedSQLiteReadSessionError("sqlite_read_session_source_changed_during_copy")
            source_path_after = source.lstat()
            if _file_stat_signature(source_path_after) != _pin_stat_signature(expected_pin):
                raise PinnedSQLiteReadSessionError("sqlite_read_session_source_path_replaced_during_copy")
            path_after = reader_path.lstat()
            _require_regular_single_link(path_after, "reader_copy")
            _assert_reader_file_identity(dest_before, path_after)
            if not _same_stat_field(path_after, "st_size", copied):
                raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_size_mismatch")
            self._assert_source_ancestor_identity(expected_pin.ancestors)
            self._assert_reader_directory_identity()
            return digest.hexdigest(), copied, path_after
        except PinnedSQLiteReadSessionCancelled:
            raise
        except PinnedSQLiteReadSessionError:
            raise
        except OSError as exc:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_io_failed") from exc
        finally:
            os.close(source_fd)
            if destination_fd is not None:
                os.close(destination_fd)

    def _pin_created_reader_copy(
        self,
        reader_path: Path,
        final_stat: os.stat_result,
        copy_sha256: str,
    ) -> SQLiteFilePinV1:
        ancestors = _directory_identity_chain(reader_path.parent, include_leaf=True)
        _require_regular_single_link(final_stat, "reader_copy")
        return _file_pin_from_stat(
            "reader_copy",
            reader_path,
            final_stat,
            copy_sha256,
            ancestors,
        )

    def _open_private_reader(self) -> None:
        reader_path = self._reader_database_path
        if reader_path is None:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_path_missing")
        self._assert_reader_directory_identity()
        if self._reader_copy_pin is None:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_pin_missing")
        try:
            uri = reader_path.as_uri() + "?mode=ro"
            connection = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5.0)
            self._connection = connection
            connection.enable_load_extension(False)
            connection.execute("PRAGMA query_only=ON")
            query_only = connection.execute("PRAGMA query_only").fetchone()
            if query_only != (1,):
                raise PinnedSQLiteReadSessionError("sqlite_read_session_query_only_not_enabled")
            database_list = connection.execute("PRAGMA database_list").fetchall()
            if len(database_list) != 1 or len(database_list[0]) < 3:
                raise PinnedSQLiteReadSessionError("sqlite_read_session_database_list_invalid")
            opened_path = _canonical_absolute_path(str(database_list[0][2]), "reader database")
            if _path_key(opened_path) != _path_key(reader_path):
                raise PinnedSQLiteReadSessionError("sqlite_read_session_opened_wrong_database")
            connection.set_authorizer(self._authorize)
            self._internal_transaction_control = True
            connection.execute("BEGIN")
            self._internal_transaction_control = False
            schema_cursor = connection.execute(
                "SELECT type, name, tbl_name, sql "
                "FROM sqlite_schema ORDER BY type, name, tbl_name, sql"
            )
            objects_list: list[SQLiteSchemaObjectV1] = []
            schema_bytes = 0
            while True:
                self._poll_cancel()
                rows = schema_cursor.fetchmany(256)
                if not rows:
                    break
                for row in rows:
                    sql_value = None if row[3] is None else str(row[3])
                    sql_size = 0 if sql_value is None else len(sql_value.encode("utf-8"))
                    if sql_size > MAX_SCHEMA_SQL_BYTES:
                        raise PinnedSQLiteReadSessionError("sqlite_read_session_schema_sql_too_large")
                    schema_bytes += sum(
                        len(str(value).encode("utf-8")) for value in row[:3]
                    ) + sql_size
                    if len(objects_list) >= MAX_SCHEMA_OBJECTS or schema_bytes > MAX_SCHEMA_TOTAL_BYTES:
                        raise PinnedSQLiteReadSessionError("sqlite_read_session_schema_too_large")
                    objects_list.append(
                        SQLiteSchemaObjectV1(
                            object_type=str(row[0]),
                            name=str(row[1]),
                            table_name=str(row[2]),
                            sql=sql_value,
                        )
                    )
            objects = tuple(objects_list)
            self._schema_objects = objects
            self._schema_sha256 = _canonical_sha256([item.to_dict() for item in objects])
            journal_mode_row = connection.execute("PRAGMA journal_mode").fetchone()
            if journal_mode_row is None or type(journal_mode_row[0]) is not str:
                raise PinnedSQLiteReadSessionError("sqlite_read_session_journal_mode_invalid")
            self._reader_journal_mode = journal_mode_row[0].lower()
            self._record_reader_sidecars()
            self._report_progress("reader_transaction_ready", 1, 1)
        except PinnedSQLiteReadSessionError:
            raise
        except sqlite3.Error as exc:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_open_failed") from exc

    def _authorize(
        self,
        action: int,
        arg1: str | None,
        arg2: str | None,
        database_name: str | None,
        source: str | None,
    ) -> int:
        del source
        allowed = {
            getattr(sqlite3, "SQLITE_SELECT", -1),
            getattr(sqlite3, "SQLITE_READ", -1),
            getattr(sqlite3, "SQLITE_FUNCTION", -1),
            getattr(sqlite3, "SQLITE_RECURSIVE", -1),
        }
        if action in allowed:
            if action == getattr(sqlite3, "SQLITE_READ", -2):
                if database_name in {"main", "temp"}:
                    return sqlite3.SQLITE_OK
                known_main_tables = {
                    item.name
                    for item in self._schema_objects
                    if item.object_type == "table"
                }
                # COUNT(*) 的 SQLite authorizer 事件會以 db_name=None、column="" 回報。
                if (
                    database_name is None
                    and arg2 == ""
                    and arg1 in known_main_tables
                ):
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY
            if action == getattr(sqlite3, "SQLITE_FUNCTION", -3) and (
                (arg1 or arg2 or "").lower() == "load_extension"
            ):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        if action == getattr(sqlite3, "SQLITE_PRAGMA", -4):
            pragma_name = (arg1 or "").lower()
            if pragma_name in _READ_ONLY_PRAGMAS and arg2 is None:
                return sqlite3.SQLITE_OK
            if pragma_name in _READ_ONLY_PRAGMAS_WITH_ARGUMENT:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        if action == getattr(sqlite3, "SQLITE_TRANSACTION", -5):
            if self._internal_transaction_control and (arg1 or "").upper() in {
                "BEGIN",
                "ROLLBACK",
            }:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_DENY

    def _record_reader_sidecars(self) -> None:
        directory = self._reader_directory
        reader_path = self._reader_database_path
        if directory is None or reader_path is None:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_directory_missing")
        self._assert_reader_directory_identity()
        expected = {
            reader_path.name,
            *(reader_path.name + suffix for suffix in _READER_SIDE_SUFFIXES),
        }
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_inventory_failed") from exc
        if len(entries) > len(expected):
            raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_inventory_overflow")
        for entry in entries:
            if entry.name not in expected:
                raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_unknown_file")
            try:
                info = (directory / entry.name).lstat()
            except OSError as exc:
                raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_stat_failed") from exc
            _require_regular_single_link(info, "reader_sidecar")
            if entry.name != reader_path.name:
                if info.st_size > MAX_SHM_BYTES and entry.name.endswith("-shm"):
                    raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_shm_too_large")
                if info.st_size > MAX_SIDECAR_BYTES:
                    raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_sidecar_too_large")
                _require_regular_single_link(info, "reader_sidecar")
                identity = (int(info.st_dev), int(info.st_ino))
                previous = self._owned_reader_sidecar_ids.get(entry.name)
                if previous is not None and previous != identity:
                    raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_sidecar_replaced")
                self._owned_reader_sidecar_ids.setdefault(entry.name, identity)
            else:
                _assert_reader_file_identity(self._reader_copy_pin_stat(), info)

    def _reader_copy_pin_stat(self) -> os.stat_result:
        pin = self._reader_copy_pin
        if pin is None:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_pin_missing")
        path = self._reader_database_path
        if path is None:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_path_missing")
        info = path.lstat()
        _require_regular_single_link(info, "reader_copy")
        if _path_file_identity(info) != (pin.device, pin.inode):
            raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_copy_replaced")
        return info

    def _capture_reader_copy_pin(self) -> SQLiteFilePinV1:
        reader_path = self._reader_database_path
        expected = self._reader_copy_pin
        if reader_path is None or expected is None:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_pin_missing")
        self._assert_reader_directory_identity()
        current_ancestors = _directory_identity_chain(reader_path.parent, include_leaf=True)
        if current_ancestors != expected.ancestors:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_copy_ancestor_changed")
        size = expected.size_bytes
        if size is None:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_size_missing")
        pin = _capture_file_pin(
            "reader_copy",
            reader_path,
            max_bytes=size,
            cancel_callback=self._poll_cancel,
            progress_callback=lambda current, total: self._report_progress(
                "verify_private_copy_bytes", current, total
            ),
            expected_ancestors=expected.ancestors,
        )
        return pin

    def _capture_source_file_group(self, stage: str) -> tuple[SQLiteFilePinV1, ...]:
        source = self._source_path
        if source is None:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_source_path_missing")
        self._poll_cancel()
        ancestor_chain = _directory_identity_chain(source.parent, include_leaf=True)
        pins: list[SQLiteFilePinV1] = []
        for role in _SOURCE_ROLES:
            suffix = {"main": "", "wal": "-wal", "shm": "-shm", "rollback_journal": "-journal"}[
                role
            ]
            path = source if role == "main" else Path(str(source) + suffix)
            cap = (
                self._max_copy_bytes
                if role == "main"
                else MAX_SHM_BYTES
                if role == "shm"
                else MAX_SIDECAR_BYTES
            )
            def report_file_progress(current: int, total: int) -> None:
                self._report_progress(f"{stage}_{role}", current, total)

            pin = _capture_file_pin(
                role,
                path,
                max_bytes=cap,
                cancel_callback=self._poll_cancel,
                progress_callback=report_file_progress,
                expected_ancestors=ancestor_chain,
            )
            pins.append(pin)
        sidecar_total = sum(
            pin.size_bytes or 0 for pin in pins[1:] if pin.present
        )
        if sidecar_total > MAX_SOURCE_SIDECAR_TOTAL_BYTES:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_source_sidecars_too_large")
        if _directory_identity_chain(source.parent, include_leaf=True) != ancestor_chain:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_source_ancestor_changed")
        return tuple(pins)

    def _assert_source_ancestor_identity(
        self,
        expected: tuple[SQLitePathIdentityV1, ...],
    ) -> None:
        source = self._source_path
        if source is None or _directory_identity_chain(source.parent, include_leaf=True) != expected:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_source_ancestor_changed")

    def _assert_private_root_unchanged(self) -> None:
        private = self._private_root
        if private is None or _directory_identity_chain(private, include_leaf=True) != self._private_root_chain:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_private_root_changed")

    def _assert_reader_directory_identity(self) -> None:
        directory = self._reader_directory
        expected = self._reader_directory_identity
        private = self._private_root
        if directory is None or expected is None or private is None:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_directory_missing")
        self._assert_private_root_unchanged()
        chain = _directory_identity_chain(directory, include_leaf=True)
        if not chain or chain != self._reader_directory_chain_start or chain[-1] != expected:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_directory_replaced")

    def _close_connection(self) -> None:
        connection = self._connection
        if connection is None:
            return
        self._internal_transaction_control = True
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error as exc:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_rollback_failed") from exc
        finally:
            self._internal_transaction_control = False
        try:
            connection.close()
        except sqlite3.Error as exc:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_connection_close_failed") from exc
        self._connection = None

    def _close_connection_safely(self) -> None:
        connection = self._connection
        if connection is None:
            return
        self._internal_transaction_control = True
        try:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            connection.close()
        except sqlite3.Error:
            pass
        finally:
            self._internal_transaction_control = False
            self._connection = None

    def _cleanup_owned_copy(self, *, suppress_errors: bool) -> None:
        directory = self._reader_directory
        expected_dir = self._reader_directory_identity
        reader_path = self._reader_database_path
        private = self._private_root
        if directory is None:
            return
        try:
            self._assert_reader_directory_identity()
            if expected_dir is None or reader_path is None or private is None:
                raise PinnedSQLiteReadSessionError("sqlite_read_session_cleanup_identity_missing")
            expected_names = {
                reader_path.name,
                *(reader_path.name + suffix for suffix in _READER_SIDE_SUFFIXES),
            }
            entries = list(os.scandir(directory))
            if any(entry.name not in expected_names for entry in entries):
                raise PinnedSQLiteReadSessionError("sqlite_read_session_cleanup_unknown_file")
            for entry in entries:
                path = directory / entry.name
                info = path.lstat()
                _require_regular_single_link(info, "cleanup_file")
                if entry.name == reader_path.name:
                    expected_copy_identity = (
                        (self._reader_copy_pin.device, self._reader_copy_pin.inode)
                        if self._reader_copy_pin is not None
                        else self._reader_copy_creation_identity
                    )
                    if expected_copy_identity is None or _path_file_identity(info) != expected_copy_identity:
                        raise PinnedSQLiteReadSessionError("sqlite_read_session_cleanup_copy_replaced")
                else:
                    expected_identity = self._owned_reader_sidecar_ids.get(entry.name)
                    if expected_identity is None or _path_file_identity(info) != expected_identity:
                        raise PinnedSQLiteReadSessionError("sqlite_read_session_cleanup_sidecar_unowned")
                self._assert_reader_directory_identity()
                current = path.lstat()
                if _path_file_identity(current) != _path_file_identity(info) or _is_link_or_reparse(current):
                    raise PinnedSQLiteReadSessionError("sqlite_read_session_cleanup_file_changed")
                os.unlink(path)
            self._assert_reader_directory_identity()
            current_dir = directory.lstat()
            if _directory_identity_from_stat(directory, current_dir) != expected_dir:
                raise PinnedSQLiteReadSessionError("sqlite_read_session_cleanup_directory_changed")
            os.rmdir(directory)
            self._reader_directory = None
            self._reader_directory_identity = None
            self._reader_directory_chain_start = ()
            self._reader_database_path = None
            self._reader_copy_creation_identity = None
        except (OSError, PinnedSQLiteReadSessionError) as exc:
            if not suppress_errors:
                if isinstance(exc, PinnedSQLiteReadSessionError):
                    raise
                raise PinnedSQLiteReadSessionError("sqlite_read_session_cleanup_failed") from exc

    def _poll_cancel(self) -> None:
        callback = self._cancel_callback
        if callback is None:
            return
        try:
            value = callback()
        except Exception as exc:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_cancel_callback_failed") from exc
        if type(value) is not bool:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_cancel_callback_not_bool")
        if value:
            raise PinnedSQLiteReadSessionCancelled()

    def _report_progress(self, stage: str, current: int, total: int) -> None:
        callback = self._progress_callback
        if callback is None:
            return
        try:
            callback(stage, current, total)
        except Exception as exc:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_progress_callback_failed") from exc


def _capture_file_pin(
    role: SQLiteFileRole,
    path: Path,
    *,
    max_bytes: int,
    cancel_callback: Callable[[], None],
    progress_callback: Callable[[int, int], None],
    expected_ancestors: tuple[SQLitePathIdentityV1, ...],
) -> SQLiteFilePinV1:
    if _directory_identity_chain(path.parent, include_leaf=True) != expected_ancestors:
        raise PinnedSQLiteReadSessionError("sqlite_read_session_source_ancestor_changed")
    try:
        before = path.lstat()
    except FileNotFoundError:
        if _path_entry_exists(path):
            raise PinnedSQLiteReadSessionError("sqlite_read_session_source_missing_race")
        ancestors_after = _directory_identity_chain(path.parent, include_leaf=True)
        if ancestors_after != expected_ancestors:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_source_ancestor_changed")
        return SQLiteFilePinV1(
            role=role,
            path=str(path),
            present=False,
            device=None,
            inode=None,
            size_bytes=None,
            mtime_ns=None,
            ctime_ns=None,
            mode=None,
            nlink=None,
            file_attributes=None,
            reparse=False,
            sha256=None,
            ancestors=expected_ancestors,
        )
    _require_regular_single_link(before, role)
    size = int(before.st_size)
    if size > max_bytes:
        raise PinnedSQLiteReadSessionError("sqlite_read_session_source_file_too_large")
    descriptor = _open_path_readonly(path, before, role)
    digest = sha256()
    read_bytes = 0
    try:
        while True:
            cancel_callback()
            block = os.read(descriptor, COPY_CHUNK_BYTES)
            if not block:
                break
            read_bytes += len(block)
            if read_bytes > max_bytes:
                raise PinnedSQLiteReadSessionError("sqlite_read_session_source_file_too_large")
            digest.update(block)
            progress_callback(read_bytes, size)
        after_fd = os.fstat(descriptor)
        after_path = path.lstat()
        _require_regular_single_link(after_fd, role)
        _require_regular_single_link(after_path, role)
        if _file_stat_signature(before) != _file_stat_signature(after_fd):
            raise PinnedSQLiteReadSessionError("sqlite_read_session_source_changed_while_hashing")
        if _file_stat_signature(before) != _file_stat_signature(after_path):
            raise PinnedSQLiteReadSessionError("sqlite_read_session_source_path_replaced")
        if read_bytes != size:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_source_size_changed")
        if _directory_identity_chain(path.parent, include_leaf=True) != expected_ancestors:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_source_ancestor_changed")
        return _file_pin_from_stat(role, path, before, digest.hexdigest(), expected_ancestors)
    except PinnedSQLiteReadSessionError:
        raise
    except OSError as exc:
        raise PinnedSQLiteReadSessionError("sqlite_read_session_source_hash_failed") from exc
    finally:
        os.close(descriptor)


def _preflight_main_size(source_path: Path, max_copy_bytes: int) -> None:
    ancestors = _directory_identity_chain(source_path.parent, include_leaf=True)
    try:
        info = source_path.lstat()
    except OSError as exc:
        raise PinnedSQLiteReadSessionError("sqlite_read_session_source_stat_failed") from exc
    _require_regular_single_link(info, "main")
    if int(info.st_size) > max_copy_bytes:
        raise PinnedSQLiteReadSessionError("sqlite_read_session_copy_cap_exceeded")
    if _directory_identity_chain(source_path.parent, include_leaf=True) != ancestors:
        raise PinnedSQLiteReadSessionError("sqlite_read_session_source_ancestor_changed")


def _open_readonly_file(path: Path, expected_pin: SQLiteFilePinV1) -> int:
    try:
        before = path.lstat()
        _require_regular_single_link(before, expected_pin.role)
        if _file_stat_signature(before) != _pin_stat_signature(expected_pin):
            raise PinnedSQLiteReadSessionError("sqlite_read_session_source_stat_changed")
        descriptor = _open_path_readonly(path, before, expected_pin.role)
        opened = os.fstat(descriptor)
        if _file_stat_signature(opened) != _pin_stat_signature(expected_pin):
            os.close(descriptor)
            raise PinnedSQLiteReadSessionError("sqlite_read_session_source_open_identity_changed")
        return descriptor
    except PinnedSQLiteReadSessionError:
        raise
    except OSError as exc:
        raise PinnedSQLiteReadSessionError("sqlite_read_session_source_open_failed") from exc


def _open_path_readonly(path: Path, expected_stat: os.stat_result, role: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        raise PinnedSQLiteReadSessionError("sqlite_read_session_file_open_failed") from exc
    try:
        opened = os.fstat(descriptor)
        _require_regular_single_link(opened, role)
        if _file_stat_signature(opened) != _file_stat_signature(expected_stat):
            raise PinnedSQLiteReadSessionError("sqlite_read_session_file_open_identity_changed")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _file_pin_from_stat(
    role: SQLiteFileRole,
    path: Path,
    info: os.stat_result,
    digest: str,
    ancestors: tuple[SQLitePathIdentityV1, ...],
) -> SQLiteFilePinV1:
    attributes = int(getattr(info, "st_file_attributes", 0))
    return SQLiteFilePinV1(
        role=role,
        path=str(path),
        present=True,
        device=int(info.st_dev),
        inode=int(info.st_ino),
        size_bytes=int(info.st_size),
        mtime_ns=int(info.st_mtime_ns),
        ctime_ns=int(info.st_ctime_ns),
        mode=int(info.st_mode),
        nlink=int(info.st_nlink),
        file_attributes=attributes,
        reparse=bool(attributes & _WINDOWS_REPARSE_POINT) or stat.S_ISLNK(info.st_mode),
        sha256=digest,
        ancestors=ancestors,
    )


def _directory_identity_chain(path: Path, *, include_leaf: bool) -> tuple[SQLitePathIdentityV1, ...]:
    absolute = Path(os.path.abspath(path))
    if not absolute.is_absolute():
        raise PinnedSQLiteReadSessionError("sqlite_read_session_directory_not_absolute")
    current = Path(absolute.anchor)
    parts = absolute.parts[1:]
    if not include_leaf and parts:
        parts = parts[:-1]
    identities: list[SQLitePathIdentityV1] = []
    for part in parts:
        current = current / part
        try:
            info = current.lstat()
        except OSError as exc:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_path_component_unavailable") from exc
        if not stat.S_ISDIR(info.st_mode) or _is_link_or_reparse(info):
            raise PinnedSQLiteReadSessionError("sqlite_read_session_reparse_or_non_directory_component")
        identities.append(_directory_identity_from_stat(current, info))
    if not identities:
        info = current.lstat()
        if not stat.S_ISDIR(info.st_mode) or _is_link_or_reparse(info):
            raise PinnedSQLiteReadSessionError("sqlite_read_session_root_not_plain_directory")
        identities.append(_directory_identity_from_stat(current, info))
    return tuple(identities)


def _directory_identity_from_stat(path: Path, info: os.stat_result) -> SQLitePathIdentityV1:
    attributes = int(getattr(info, "st_file_attributes", 0))
    return SQLitePathIdentityV1(
        path=str(path),
        device=int(info.st_dev),
        inode=int(info.st_ino),
        mode=int(info.st_mode),
        file_attributes=attributes,
        reparse=bool(attributes & _WINDOWS_REPARSE_POINT) or stat.S_ISLNK(info.st_mode),
    )


def _require_regular_single_link(info: os.stat_result, role: str) -> None:
    if _is_link_or_reparse(info):
        raise PinnedSQLiteReadSessionError(f"sqlite_read_session_reparse_file:{role}")
    if not stat.S_ISREG(info.st_mode):
        raise PinnedSQLiteReadSessionError(f"sqlite_read_session_not_regular_file:{role}")
    if type(getattr(info, "st_nlink", None)) is not int or info.st_nlink != 1:
        raise PinnedSQLiteReadSessionError(f"sqlite_read_session_hardlink_rejected:{role}")
    if type(getattr(info, "st_ino", None)) is not int or info.st_ino == 0:
        raise PinnedSQLiteReadSessionError(f"sqlite_read_session_file_identity_unavailable:{role}")


def _is_link_or_reparse(info: os.stat_result) -> bool:
    attributes = int(getattr(info, "st_file_attributes", 0))
    return stat.S_ISLNK(info.st_mode) or bool(attributes & _WINDOWS_REPARSE_POINT)


def _file_stat_signature(info: os.stat_result) -> dict[str, int]:
    return {
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "size": int(info.st_size),
        "mtime_ns": int(info.st_mtime_ns),
        "ctime_ns": int(info.st_ctime_ns),
        "mode": int(info.st_mode),
        "nlink": int(info.st_nlink),
        "file_attributes": int(getattr(info, "st_file_attributes", 0)),
    }


def _pin_stat_signature(pin: SQLiteFilePinV1) -> dict[str, int]:
    if not pin.present:
        raise PinnedSQLiteReadSessionError("sqlite_read_session_missing_file_pin")
    values = {
        "device": pin.device,
        "inode": pin.inode,
        "size": pin.size_bytes,
        "mtime_ns": pin.mtime_ns,
        "ctime_ns": pin.ctime_ns,
        "mode": pin.mode,
        "nlink": pin.nlink,
        "file_attributes": pin.file_attributes,
    }
    if any(type(value) is not int for value in values.values()):
        raise PinnedSQLiteReadSessionError("sqlite_read_session_file_pin_incomplete")
    complete: dict[str, int] = {}
    for key, value in values.items():
        if type(value) is not int:
            raise PinnedSQLiteReadSessionError("sqlite_read_session_file_pin_incomplete")
        complete[key] = value
    return complete


def _path_file_identity(info: os.stat_result) -> tuple[int, int]:
    return int(info.st_dev), int(info.st_ino)


def _assert_reader_file_identity(before: os.stat_result, after: os.stat_result) -> None:
    if _path_file_identity(before) != _path_file_identity(after):
        raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_file_replaced")
    if stat.S_IFMT(before.st_mode) != stat.S_IFMT(after.st_mode):
        raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_file_mode_changed")
    if _is_link_or_reparse(after) or int(after.st_nlink) != 1:
        raise PinnedSQLiteReadSessionError("sqlite_read_session_reader_file_link_changed")


def _same_stat_field(info: os.stat_result, name: str, expected: int) -> bool:
    return int(getattr(info, name)) == expected


def _canonical_absolute_path(value: Path | str, name: str) -> Path:
    raw = Path(value)
    if not raw.is_absolute() or any(part == ".." for part in raw.parts):
        raise PinnedSQLiteReadSessionError(f"sqlite_read_session_{name}_not_canonical_absolute")
    absolute = Path(os.path.abspath(raw))
    return absolute


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def _path_is_within(candidate: Path, parent: Path) -> bool:
    candidate_key = _path_key(candidate)
    parent_key = _path_key(parent)
    try:
        return os.path.commonpath((candidate_key, parent_key)) == parent_key
    except ValueError:
        return False


def _path_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise PinnedSQLiteReadSessionError("sqlite_read_session_path_stat_failed") from exc
    return True


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(raw).hexdigest()
