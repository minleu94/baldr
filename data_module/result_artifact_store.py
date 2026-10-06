"""低階推薦執行 artifact store；只處理 bytes、hash 與索引 metadata。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import ctypes
from collections.abc import Iterable
from typing import Iterator, cast


_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ARTIFACT_NAME_PATTERN = re.compile(r"[0-9a-f]{64}\.json\Z")


class ResultArtifactStoreError(RuntimeError):
    """artifact store 的明確錯誤基底。"""


class ResultArtifactConflict(ResultArtifactStoreError):
    """同一 opaque identity 已綁定不同 bytes 或 payload hash。"""


class ResultArtifactIntegrityError(ResultArtifactStoreError):
    """artifact、index 或儲存路徑無法通過完整性檢查。"""


class ResultArtifactIndexError(ResultArtifactStoreError):
    """SQLite index 無法讀寫；已發布的 artifact 會保留供重試。"""


class ResultArtifactPostPublishIndexError(ResultArtifactIndexError):
    """artifact 已 create-only 發布，但 identity metadata commit 失敗。"""


class ResultArtifactPublishError(ResultArtifactStoreError):
    """artifact 無法 create-only 發布。"""


@dataclass(frozen=True, slots=True)
class ArtifactIndexMetadata:
    """一次新 artifact 的 typed index metadata；不含業務 DTO。"""

    result_id: str
    payload_hash: str
    artifact_sha256: str
    schema_version: str
    schema_revision: int
    label: str | None
    notes: str | None
    persisted_at: str | None

    def __post_init__(self) -> None:
        if type(self.result_id) is not str or not self.result_id.strip():
            raise ValueError("result_id 必須是非空白字串")
        if type(self.payload_hash) is not str or _HASH_PATTERN.fullmatch(self.payload_hash) is None:
            raise ValueError("payload_hash 必須是 sha256:<64 小寫 hex>")
        if type(self.artifact_sha256) is not str or _HASH_PATTERN.fullmatch(self.artifact_sha256) is None:
            raise ValueError("artifact_sha256 必須是 sha256:<64 小寫 hex>")
        if type(self.schema_version) is not str or not self.schema_version.strip():
            raise ValueError("schema_version 必須是非空白字串")
        if type(self.schema_revision) is not int or self.schema_revision < 1:
            raise ValueError("schema_revision 必須是正整數")
        if self.label is not None and type(self.label) is not str:
            raise TypeError("label 必須是 str 或 None")
        if self.notes is not None and type(self.notes) is not str:
            raise TypeError("notes 必須是 str 或 None")
        if self.persisted_at is not None and type(self.persisted_at) is not str:
            raise TypeError("persisted_at 必須是 str 或 None")


@dataclass(frozen=True, slots=True)
class ArtifactIndexRecord:
    """可重建 projection 與獨立 mutable metadata 的讀取結果。"""

    metadata: ArtifactIndexMetadata
    artifact_name: str
    metadata_present: bool
    metadata_payload_hash: str | None


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """目錄掃描取得的 artifact bytes；呼叫端負責解碼其格式。"""

    artifact_name: str
    payload: bytes


class ResultArtifactStore:
    """以固定安全檔名發布 immutable bytes，並維護可重建 SQLite projection。

    `result_artifact_index` 是由 artifact bytes 重建的查詢 projection；
    `result_artifact_metadata` 是 label、notes、persisted_at 的可變權威。
    若整個 SQLite database 遺失，artifact 可重建 identity/hash/schema，但
    原 metadata 無法從 immutable execution 推導。
    """

    _INDEX_TABLE = "result_artifact_index"
    _METADATA_TABLE = "result_artifact_metadata"

    def __init__(self, artifact_root: Path, database_path: Path) -> None:
        self.artifact_root = Path(artifact_root)
        self.database_path = Path(database_path)
        self._validate_config()

    def _validate_config(self, *, integrity_error: bool = False) -> None:
        root = Path(os.path.abspath(self.artifact_root))
        database = Path(os.path.abspath(self.database_path))
        valid = (
            root.name == "execution_artifacts"
            and root.parent.name == "runs"
            and database.name == "recommendation_runs.db"
            and root.parent == database.parent
        )
        if not valid:
            message = (
                "R012 store 必須使用同一 runs 目錄下的 "
                "execution_artifacts/ 與 recommendation_runs.db"
            )
            if integrity_error:
                raise ResultArtifactIntegrityError(message)
            raise ValueError(message)

    @staticmethod
    def _is_symlink_or_reparse(path: Path) -> bool:
        if path.is_symlink():
            return True
        if os.name != "nt":
            return False
        try:
            attributes = getattr(path.lstat(), "st_file_attributes", 0)
        except FileNotFoundError:
            return False
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
        return bool(attributes & reparse_flag)

    @staticmethod
    def artifact_name_for(result_id: str) -> str:
        """以 opaque ID 的 UTF-8 SHA-256 做固定小寫檔名，避免路徑語意。"""

        if type(result_id) is not str or not result_id.strip():
            raise ValueError("result_id 必須是非空白字串")
        try:
            identity_bytes = result_id.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError("result_id 必須能以 UTF-8 精確編碼") from exc
        return hashlib.sha256(identity_bytes).hexdigest() + ".json"

    def _ensure_layout(self, *, create_artifact_root: bool = False) -> bool:
        self._validate_config(integrity_error=True)
        database_parent = self.database_path.parent
        if self._is_symlink_or_reparse(database_parent) or self._is_symlink_or_reparse(self.artifact_root):
            raise ResultArtifactIntegrityError("database/artifact root 不可為 symlink")
        if self._is_symlink_or_reparse(self.database_path):
            raise ResultArtifactIntegrityError("database path 不可為 symlink")
        if create_artifact_root:
            try:
                database_parent.mkdir(parents=True, exist_ok=True)
                self.artifact_root.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ResultArtifactPublishError("無法建立 artifact store 目錄") from exc
        elif not database_parent.exists():
            return False
        if self._is_symlink_or_reparse(database_parent) or self._is_symlink_or_reparse(self.artifact_root):
            raise ResultArtifactIntegrityError("database/artifact root 不可為 symlink")
        if self._is_symlink_or_reparse(self.database_path):
            raise ResultArtifactIntegrityError("database path 不可為 symlink")
        try:
            resolved_parent = database_parent.resolve(strict=True)
            resolved_root_parent = self.artifact_root.parent.resolve(strict=True)
        except OSError as exc:
            raise ResultArtifactIntegrityError("artifact store root 無法解析") from exc
        if resolved_root_parent != resolved_parent:
            raise ResultArtifactIntegrityError(
                "artifact root 必須是 SQLite database 目錄的直接子目錄"
            )
        return True

    def _artifact_path(self, result_id: str, *, create_root: bool = False) -> Path:
        self._ensure_layout(create_artifact_root=create_root)
        name = self.artifact_name_for(result_id)
        path = self.artifact_root / name
        if not self.artifact_root.exists():
            return path
        try:
            if path.parent.resolve(strict=True) != self.artifact_root.resolve(strict=True):
                raise ResultArtifactIntegrityError("artifact path 超出設定 root")
        except OSError as exc:
            raise ResultArtifactIntegrityError("artifact path root 無法解析") from exc
        if self._is_symlink_or_reparse(path):
            raise ResultArtifactIntegrityError("artifact file 不可為 symlink")
        return path

    @staticmethod
    def _windows_open_no_follow(path: Path, *, directory: bool) -> int:
        """Open a Windows path itself (not a reparse target) and validate its handle.

        A `Path.is_symlink()`/`lstat()` check followed by `os.open()` has a race on
        Windows because Python does not expose `O_NOFOLLOW` there.  `OPEN_REPARSE_POINT`
        makes the handle refer to the directory entry itself; the attribute check is
        then made against that same held handle.  Sharing intentionally omits
        `FILE_SHARE_DELETE` so the opened root/file cannot be swapped while it is in use.
        """

        import msvcrt
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL
        get_info = kernel32.GetFileInformationByHandleEx
        get_info.argtypes = (
            wintypes.HANDLE,
            wintypes.INT,
            wintypes.LPVOID,
            wintypes.DWORD,
        )
        get_info.restype = wintypes.BOOL

        class _FileAttributeTagInfo(ctypes.Structure):
            _fields_ = (("attributes", wintypes.DWORD), ("reparse_tag", wintypes.DWORD))

        generic_read = 0x80000000
        file_read_attributes = 0x00000080
        share_read_write = 0x00000001 | 0x00000002
        open_existing = 3
        open_reparse_point = 0x00200000
        backup_semantics = 0x02000000
        sequential_scan = 0x08000000
        info_class_file_attribute_tag = 9
        file_attribute_directory = 0x00000010
        file_attribute_reparse_point = 0x00000400
        invalid_handle = ctypes.c_void_p(-1).value

        desired_access = file_read_attributes if directory else generic_read
        flags = open_reparse_point | (backup_semantics if directory else sequential_scan)
        handle = create_file(
            str(path),
            desired_access,
            share_read_write,
            None,
            open_existing,
            flags,
            None,
        )
        handle_value = handle if isinstance(handle, int) else getattr(handle, "value", None)
        if handle_value is None or handle_value == invalid_handle:
            error = ctypes.get_last_error()
            if error in (2, 3):
                raise FileNotFoundError(error, os.strerror(error), str(path))
            raise OSError(error, f"CreateFileW failed for {path}")

        try:
            info = _FileAttributeTagInfo()
            if not get_info(
                handle,
                info_class_file_attribute_tag,
                ctypes.byref(info),
                ctypes.sizeof(info),
            ):
                error = ctypes.get_last_error()
                raise OSError(error, f"GetFileInformationByHandleEx failed for {path}")
            if info.attributes & file_attribute_reparse_point:
                raise ResultArtifactIntegrityError("artifact path 是 Windows reparse point")
            is_directory = bool(info.attributes & file_attribute_directory)
            if is_directory != directory:
                raise ResultArtifactIntegrityError(
                    "artifact root 必須是目錄，artifact payload 必須是一般檔案"
                )
            if directory:
                result = int(handle_value)
                handle_value = None
                return result
            descriptor = msvcrt.open_osfhandle(
                int(handle_value), os.O_RDONLY | getattr(os, "O_BINARY", 0)
            )
            handle_value = None
            return descriptor
        finally:
            if handle_value is not None:
                close_handle(handle)

    @staticmethod
    def _windows_close_handle(handle: int) -> None:
        from ctypes import wintypes

        close_handle = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL
        if not close_handle(handle):
            error = ctypes.get_last_error()
            raise OSError(error, "CloseHandle failed")

    def _read_path(self, path: Path) -> bytes | None:
        if self._is_symlink_or_reparse(path):
            raise ResultArtifactIntegrityError("artifact file 不可為 symlink")
        if os.name == "nt":
            root_handle: int | None = None
            descriptor: int | None = None
            try:
                root_handle = self._windows_open_no_follow(path.parent, directory=True)
                descriptor = self._windows_open_no_follow(path, directory=False)
            except FileNotFoundError:
                return None
            except ResultArtifactStoreError:
                raise
            except OSError as exc:
                raise ResultArtifactIntegrityError(
                    f"無法以 no-follow handle 讀取 artifact: {path.name}"
                ) from exc
            finally:
                if root_handle is not None:
                    self._windows_close_handle(root_handle)
            assert descriptor is not None
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode):
                    raise ResultArtifactIntegrityError("artifact 必須是一般檔案")
                with os.fdopen(descriptor, "rb") as handle:
                    descriptor = -1
                    return handle.read()
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
        try:
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ResultArtifactIntegrityError(f"無法安全讀取 artifact: {path.name}") from exc
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise ResultArtifactIntegrityError("artifact 必須是一般檔案")
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                return handle.read()
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    @staticmethod
    def _legacy_run_exists(connection: sqlite3.Connection, result_id: str) -> bool:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'runs'"
        ).fetchone()
        if table is None:
            return False
        return connection.execute(
            "SELECT 1 FROM runs WHERE result_id = ? LIMIT 1", (result_id,)
        ).fetchone() is not None

    @staticmethod
    def _claim_identity_metadata(
        connection: sqlite3.Connection, metadata: ArtifactIndexMetadata
    ) -> None:
        """Commit the ID/hash authority only after artifact bytes are published."""

        connection.execute(
            """
            INSERT OR IGNORE INTO result_artifact_metadata
            (result_id, payload_hash, label, notes, persisted_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                metadata.result_id,
                metadata.payload_hash,
                metadata.label,
                metadata.notes,
                metadata.persisted_at,
            ),
        )

    def has_legacy_run(self, result_id: str) -> bool:
        """Check old `runs` identity without creating a database/schema."""

        if not self._ensure_layout() or not self.database_path.exists():
            return False
        try:
            connection = self._connect()
            try:
                return self._legacy_run_exists(connection, result_id)
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise ResultArtifactIndexError("無法讀取 legacy runs identity") from exc

    @staticmethod
    def _raw_hash(payload: bytes) -> str:
        return "sha256:" + hashlib.sha256(payload).hexdigest()

    def _legacy_file_orphan_exists(self, result_id: str) -> bool:
        """Detect the legacy ``runs/<id>.json`` orphan without reading it.

        The old repository uses the opaque ID directly in this path.  Mirror
        that exact name for collision detection, but use ``lstat`` so a final
        symlink is also treated as occupied and never followed/read.
        """

        legacy_path = self.database_path.parent / f"{result_id}.json"
        try:
            legacy_path.lstat()
        except FileNotFoundError:
            return False
        except ValueError:
            # Embedded NUL cannot name a file on supported operating systems,
            # so the legacy repository cannot have created this exact path.
            if "\x00" in result_id:
                return False
            raise ResultArtifactIntegrityError(
                "無法安全檢查 legacy result artifact path"
            )
        except OSError as exc:
            if os.name == "nt" and getattr(exc, "winerror", None) in (123, 161):
                # Win32 rejects this spelling before any file can occupy it.
                return False
            raise ResultArtifactIntegrityError(
                "無法安全檢查 legacy result artifact path"
            ) from exc
        return True

    def read_artifact(self, result_id: str) -> bytes | None:
        """按 identity 讀取；此方法不解碼，也不信任 SQLite path 欄位。"""

        path = self._artifact_path(result_id)
        if not self.artifact_root.exists():
            return None
        return self._read_path(path)

    def publish_artifact(self, payload: bytes, metadata: ArtifactIndexMetadata) -> Path:
        """鎖住跨 writer identity，durable create 後記錄 metadata claim。"""

        if type(payload) is not bytes:
            raise TypeError("artifact payload 必須是 bytes")
        if self._raw_hash(payload) != metadata.artifact_sha256:
            raise ResultArtifactIntegrityError("index raw hash 與待發布 bytes 不符")
        path = self._artifact_path(metadata.result_id, create_root=True)
        temporary_path: Path | None = None
        root_handle: int | None = None
        artifact_published = False
        connection: sqlite3.Connection | None = None
        try:
            if not self._ensure_schema(create=True):
                raise ResultArtifactIndexError("無法初始化 execution identity metadata")
            connection = self._connect()
            connection.execute("BEGIN IMMEDIATE")
            if self._legacy_run_exists(connection, metadata.result_id):
                raise ResultArtifactConflict(
                    "同一 result_id 已由 legacy runs namespace 使用"
                )
            if self._legacy_file_orphan_exists(metadata.result_id):
                raise ResultArtifactConflict(
                    "同一 result_id 已有 legacy file-only artifact；保留舊檔供 legacy recovery"
                )
            identity_row = connection.execute(
                "SELECT payload_hash FROM result_artifact_metadata WHERE result_id = ?",
                (metadata.result_id,),
            ).fetchone()
            if identity_row is not None and identity_row[0] != metadata.payload_hash:
                raise ResultArtifactConflict(
                    "同一 result_id 的 metadata authority 已綁定不同 payload_hash"
                )
            if os.name == "nt":
                # Keep the checked root directory object open without delete sharing
                # for path-based temp/create-only-link operations.
                root_handle = self._windows_open_no_follow(self.artifact_root, directory=True)
            descriptor, temporary = tempfile.mkstemp(
                prefix=".result-artifact-", suffix=".tmp", dir=self.artifact_root
            )
            temporary_path = Path(temporary)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary_path, path, follow_symlinks=False)
            except FileExistsError:
                if self._is_symlink_or_reparse(path):
                    raise ResultArtifactIntegrityError("artifact file 不可為 symlink")
                existing = self._read_path(path)
                if existing is None:
                    raise ResultArtifactIntegrityError("artifact 在 create race 中消失")
                if existing != payload:
                    raise ResultArtifactConflict(
                        "相同 result_id 已有不同 artifact bytes；拒絕覆寫"
                    )
            self._fsync_directory()
            artifact_published = True
            self._claim_identity_metadata(connection, metadata)
            connection.commit()
            return path
        except ResultArtifactStoreError:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error as exc:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            if artifact_published:
                raise ResultArtifactPostPublishIndexError(
                    "artifact 已發布；metadata claim commit 失敗，可同 ID/hash 重試"
                ) from exc
            raise ResultArtifactIndexError(
                "發布前無法取得或驗證 SQLite identity lock"
            ) from exc
        except OSError as exc:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise ResultArtifactPublishError(
                f"artifact create-only publish 失敗: {path.name}"
            ) from exc
        finally:
            if connection is not None:
                connection.close()
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    # 留下的只會是同一受控目錄內的暫存檔；不觸碰 immutable artifact。
                    pass
            if root_handle is not None:
                self._windows_close_handle(root_handle)

    def _fsync_directory(self) -> None:
        if os.name == "nt":
            return
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(self.artifact_root, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path, timeout=30.0)

    def _ensure_schema(self, *, create: bool = False) -> bool:
        if not self._ensure_layout():
            return False
        if not create and not self.database_path.exists():
            return False
        try:
            connection = self._connect()
            try:
                existing_tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' "
                        "AND name IN (?, ?)",
                        (self._INDEX_TABLE, self._METADATA_TABLE),
                    ).fetchall()
                }
                if not create:
                    return {
                        self._INDEX_TABLE,
                        self._METADATA_TABLE,
                    }.issubset(existing_tables)
                # DDL 只由明示 writer 呼叫；讀取／import／app startup 不發布 schema。
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS result_artifact_index (
                        result_id TEXT PRIMARY KEY COLLATE BINARY,
                        artifact_name TEXT NOT NULL,
                        payload_hash TEXT NOT NULL,
                        artifact_sha256 TEXT NOT NULL,
                        schema_version TEXT NOT NULL,
                        schema_revision INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS result_artifact_metadata (
                        result_id TEXT PRIMARY KEY COLLATE BINARY,
                        payload_hash TEXT NOT NULL,
                        label TEXT,
                        notes TEXT,
                        persisted_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_result_artifact_metadata_persisted_at
                        ON result_artifact_metadata(persisted_at);
                    """
                )
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise ResultArtifactIndexError("無法初始化推薦 execution SQLite tables") from exc
        return True

    @staticmethod
    def _metadata_from_row(row: tuple[object, ...]) -> ArtifactIndexRecord:
        (
            result_id,
            artifact_name,
            payload_hash,
            artifact_sha256,
            schema_version,
            schema_revision,
            metadata_payload_hash,
            label,
            notes,
            persisted_at,
            metadata_present,
        ) = row
        if not all(type(value) is str for value in (result_id, artifact_name, payload_hash, artifact_sha256, schema_version)):
            raise ResultArtifactIntegrityError("SQLite artifact index 含非法 scalar")
        if type(schema_revision) is not int:
            raise ResultArtifactIntegrityError("SQLite schema_revision 型別錯誤")
        if type(metadata_present) is not int or metadata_present not in (0, 1):
            raise ResultArtifactIntegrityError("SQLite metadata presence flag 型別錯誤")
        if label is not None and type(label) is not str:
            raise ResultArtifactIntegrityError("SQLite label 型別錯誤")
        if notes is not None and type(notes) is not str:
            raise ResultArtifactIntegrityError("SQLite notes 型別錯誤")
        if persisted_at is not None and type(persisted_at) is not str:
            raise ResultArtifactIntegrityError("SQLite persisted_at 型別錯誤")
        if metadata_present and metadata_payload_hash != payload_hash:
            raise ResultArtifactIntegrityError("mutable metadata payload hash 與 artifact identity 不符")
        if metadata_payload_hash is not None and type(metadata_payload_hash) is not str:
            raise ResultArtifactIntegrityError("SQLite metadata payload_hash 型別錯誤")
        metadata = ArtifactIndexMetadata(
            result_id=cast(str, result_id),
            payload_hash=cast(str, payload_hash),
            artifact_sha256=cast(str, artifact_sha256),
            schema_version=cast(str, schema_version),
            schema_revision=schema_revision,
            label=label,
            notes=notes,
            persisted_at=persisted_at,
        )
        return ArtifactIndexRecord(
            metadata=metadata,
            artifact_name=cast(str, artifact_name),
            metadata_present=metadata_present == 1,
            metadata_payload_hash=cast(str | None, metadata_payload_hash),
        )

    def _select_record(
        self, connection: sqlite3.Connection, result_id: str
    ) -> ArtifactIndexRecord | None:
        row = connection.execute(
            """
            SELECT i.result_id, i.artifact_name, i.payload_hash, i.artifact_sha256,
                   i.schema_version, i.schema_revision, m.payload_hash, m.label, m.notes,
                   m.persisted_at, CASE WHEN m.result_id IS NULL THEN 0 ELSE 1 END
              FROM result_artifact_index AS i
              LEFT JOIN result_artifact_metadata AS m USING (result_id)
             WHERE i.result_id = ?
            """,
            (result_id,),
        ).fetchone()
        return self._metadata_from_row(row) if row is not None else None

    def get_index(self, result_id: str) -> ArtifactIndexRecord | None:
        if not self._ensure_schema():
            return None
        try:
            connection = self._connect()
            try:
                record = self._select_record(connection, result_id)
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise ResultArtifactIndexError("無法讀取 execution index") from exc
        if record is not None:
            expected_name = self.artifact_name_for(result_id)
            if record.artifact_name != expected_name:
                raise ResultArtifactIntegrityError("SQLite index artifact name 不符 identity mapping")
        return record

    def get_identity_payload_hash(self, result_id: str) -> str | None:
        """Return the mutable-metadata identity binding, even if projection is absent."""

        if not self._ensure_schema():
            return None
        try:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT payload_hash FROM result_artifact_metadata WHERE result_id = ?",
                    (result_id,),
                ).fetchone()
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise ResultArtifactIndexError("無法讀取 execution identity metadata") from exc
        if row is None:
            return None
        payload_hash = row[0]
        if type(payload_hash) is not str or _HASH_PATTERN.fullmatch(payload_hash) is None:
            raise ResultArtifactIntegrityError("mutable metadata 含非法 payload_hash")
        return payload_hash

    def list_index_records(self) -> tuple[ArtifactIndexRecord, ...]:
        if not self._ensure_schema():
            return ()
        try:
            connection = self._connect()
            try:
                rows = connection.execute(
                    """
                    SELECT i.result_id, i.artifact_name, i.payload_hash, i.artifact_sha256,
                           i.schema_version, i.schema_revision, m.payload_hash, m.label, m.notes,
                           m.persisted_at, CASE WHEN m.result_id IS NULL THEN 0 ELSE 1 END
                      FROM result_artifact_index AS i
                      LEFT JOIN result_artifact_metadata AS m USING (result_id)
                     ORDER BY m.persisted_at DESC, i.result_id COLLATE BINARY
                    """
                    ).fetchall()
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise ResultArtifactIndexError("無法列出 execution index") from exc
        records = tuple(self._metadata_from_row(row) for row in rows)
        for record in records:
            if record.artifact_name != self.artifact_name_for(record.metadata.result_id):
                raise ResultArtifactIntegrityError("SQLite index artifact name 不符 identity mapping")
        return records

    def index_artifact(
        self,
        metadata: ArtifactIndexMetadata,
        *,
        repair_projection: bool = False,
    ) -> ArtifactIndexRecord:
        """在驗證 durable bytes 後提交／修復 projection 與初始 metadata。"""

        if not self._ensure_schema(create=True):
            raise ResultArtifactIndexError("無法在 artifact root 建立 SQLite index")
        artifact_name = self.artifact_name_for(metadata.result_id)
        artifact_path = self._artifact_path(metadata.result_id)
        existing_bytes = self._read_path(artifact_path)
        if existing_bytes is None:
            raise ResultArtifactIntegrityError("不可建立指向缺失 artifact 的 index")
        if self._raw_hash(existing_bytes) != metadata.artifact_sha256:
            raise ResultArtifactIntegrityError("artifact raw hash 與 index metadata 不符")

        try:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                if self._legacy_run_exists(connection, metadata.result_id):
                    raise ResultArtifactConflict(
                        "同一 result_id 已由 legacy runs namespace 使用"
                    )
                metadata_row = connection.execute(
                    "SELECT payload_hash FROM result_artifact_metadata WHERE result_id = ?",
                    (metadata.result_id,),
                ).fetchone()
                if metadata_row is not None and metadata_row[0] != metadata.payload_hash:
                    raise ResultArtifactConflict(
                        "既有 metadata 綁定不同 payload_hash；拒絕重用 result_id"
                    )
                existing = self._select_record(connection, metadata.result_id)
                if existing is not None:
                    old = existing.metadata
                    index_matches = (
                        existing.artifact_name == artifact_name
                        and old.payload_hash == metadata.payload_hash
                        and old.artifact_sha256 == metadata.artifact_sha256
                        and old.schema_version == metadata.schema_version
                        and old.schema_revision == metadata.schema_revision
                    )
                    if not index_matches and not repair_projection:
                        raise ResultArtifactConflict(
                            "同一 result_id 的既有 index hash/schema 不同；拒絕覆寫"
                        )
                    if not index_matches:
                        connection.execute(
                            """
                            UPDATE result_artifact_index
                               SET artifact_name = ?, payload_hash = ?, artifact_sha256 = ?,
                                   schema_version = ?, schema_revision = ?
                             WHERE result_id = ?
                            """,
                            (
                                artifact_name,
                                metadata.payload_hash,
                                metadata.artifact_sha256,
                                metadata.schema_version,
                                metadata.schema_revision,
                                metadata.result_id,
                            ),
                        )
                else:
                    connection.execute(
                        """
                        INSERT INTO result_artifact_index
                        (result_id, artifact_name, payload_hash, artifact_sha256,
                         schema_version, schema_revision)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            metadata.result_id,
                            artifact_name,
                            metadata.payload_hash,
                            metadata.artifact_sha256,
                            metadata.schema_version,
                            metadata.schema_revision,
                        ),
                    )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO result_artifact_metadata
                    (result_id, payload_hash, label, notes, persisted_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        metadata.result_id,
                        metadata.payload_hash,
                        metadata.label,
                        metadata.notes,
                        metadata.persisted_at,
                    ),
                )
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()
        except ResultArtifactStoreError:
            raise
        except sqlite3.Error as exc:
            raise ResultArtifactIndexError(
                "artifact 已 durable；SQLite index commit 失敗，可同 ID/hash 重試"
            ) from exc
        record = self.get_index(metadata.result_id)
        if record is None:
            raise ResultArtifactIndexError("SQLite commit 後找不到已寫入 index")
        return record

    def restore_missing_metadata(self, metadata: ArtifactIndexMetadata) -> ArtifactIndexRecord:
        """只補缺失 metadata；已明示 rename/notes 永遠優先保留。"""

        if not self._ensure_schema():
            raise ResultArtifactIndexError("execution index 尚未建立")
        try:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                indexed = self._select_record(connection, metadata.result_id)
                if indexed is None:
                    raise KeyError(metadata.result_id)
                current = indexed.metadata
                if (
                    current.payload_hash != metadata.payload_hash
                    or current.artifact_sha256 != metadata.artifact_sha256
                    or (
                        indexed.metadata_payload_hash is not None
                        and indexed.metadata_payload_hash != metadata.payload_hash
                    )
                ):
                    raise ResultArtifactConflict("metadata recovery identity/hash 不符")
                if indexed.metadata_present:
                    connection.execute(
                        """
                        UPDATE result_artifact_metadata
                           SET label = COALESCE(label, ?),
                               notes = COALESCE(notes, ?),
                               persisted_at = COALESCE(persisted_at, ?)
                         WHERE result_id = ?
                        """,
                        (
                            metadata.label,
                            metadata.notes,
                            metadata.persisted_at,
                            metadata.result_id,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO result_artifact_metadata
                        (result_id, payload_hash, label, notes, persisted_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            metadata.result_id,
                            metadata.payload_hash,
                            metadata.label,
                            metadata.notes,
                            metadata.persisted_at,
                        ),
                    )
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()
        except (KeyError, ResultArtifactStoreError):
            raise
        except sqlite3.Error as exc:
            raise ResultArtifactIndexError("缺失 metadata recovery 失敗") from exc
        record = self.get_index(metadata.result_id)
        if record is None:
            raise ResultArtifactIndexError("metadata recovery 後找不到 index")
        return record

    def iter_artifacts(self) -> Iterator[StoredArtifact]:
        """列舉本 store namespace 的一般檔案，不解析或猜測 wire schema。"""

        if not self._ensure_layout():
            return
        if not self.artifact_root.exists():
            return
        for path in sorted(self.artifact_root.iterdir(), key=lambda item: item.name):
            if path.name.startswith(".result-artifact-") and path.suffix == ".tmp":
                continue
            if _ARTIFACT_NAME_PATTERN.fullmatch(path.name) is None:
                continue
            if self._is_symlink_or_reparse(path):
                raise ResultArtifactIntegrityError("artifact inventory 遇到 symlink")
            payload = self._read_path(path)
            if payload is None:
                raise ResultArtifactIntegrityError("artifact inventory 中檔案消失")
            yield StoredArtifact(path.name, payload)

    def rebuild_index_projection(
        self, entries: Iterable[tuple[bytes, ArtifactIndexMetadata]]
    ) -> tuple[ArtifactIndexRecord, ...]:
        """在線性化的 writer transaction 中 inventory 並替換 projection。

        ``entries`` may be a lazy artifact inventory.  It is deliberately
        consumed only after ``BEGIN IMMEDIATE`` so a successful concurrent
        publisher is either included in this inventory or publishes/indexes
        after the rebuild commits; an older snapshot cannot erase its row.
        """

        if not self._ensure_schema(create=True):
            raise ResultArtifactIndexError("無法建立 execution index projection")

        try:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                inventory = tuple(entries)
                seen_ids: set[str] = set()
                for payload, metadata in inventory:
                    if type(payload) is not bytes:
                        raise TypeError("rebuild entry payload 必須是 bytes")
                    if metadata.result_id in seen_ids:
                        raise ResultArtifactConflict("rebuild inventory 含重複 result_id")
                    seen_ids.add(metadata.result_id)
                    if self._raw_hash(payload) != metadata.artifact_sha256:
                        raise ResultArtifactIntegrityError("rebuild entry raw hash 不符")
                    artifact_path = self._artifact_path(metadata.result_id)
                    stored = self._read_path(artifact_path)
                    if stored != payload:
                        raise ResultArtifactIntegrityError(
                            "rebuild entry 與 immutable artifact bytes 不符"
                        )
                for _, metadata in inventory:
                    if self._legacy_run_exists(connection, metadata.result_id):
                        raise ResultArtifactConflict(
                            "rebuild result_id 已由 legacy runs namespace 使用"
                        )
                    row = connection.execute(
                        "SELECT payload_hash FROM result_artifact_metadata WHERE result_id = ?",
                        (metadata.result_id,),
                    ).fetchone()
                    if row is not None and row[0] != metadata.payload_hash:
                        raise ResultArtifactConflict(
                            "metadata authority 綁定不同 payload_hash；拒絕重建"
                        )
                connection.execute("DELETE FROM result_artifact_index")
                for _, metadata in inventory:
                    connection.execute(
                        """
                        INSERT INTO result_artifact_index
                        (result_id, artifact_name, payload_hash, artifact_sha256,
                         schema_version, schema_revision)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            metadata.result_id,
                            self.artifact_name_for(metadata.result_id),
                            metadata.payload_hash,
                            metadata.artifact_sha256,
                            metadata.schema_version,
                            metadata.schema_revision,
                        ),
                    )
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()
        except ResultArtifactStoreError:
            raise
        except sqlite3.Error as exc:
            raise ResultArtifactIndexError("重建 execution index projection 失敗") from exc
        return self.list_index_records()

    def rename(self, result_id: str, label: str) -> ArtifactIndexRecord:
        if type(label) is not str:
            raise TypeError("label 必須是 str")
        return self._update_mutable_metadata(result_id, label=label, update_label=True)

    def update_notes(self, result_id: str, notes: str) -> ArtifactIndexRecord:
        if type(notes) is not str:
            raise TypeError("notes 必須是 str")
        return self._update_mutable_metadata(result_id, notes=notes, update_notes=True)

    def _update_mutable_metadata(
        self,
        result_id: str,
        *,
        label: str | None = None,
        notes: str | None = None,
        update_label: bool = False,
        update_notes: bool = False,
    ) -> ArtifactIndexRecord:
        if not self._ensure_schema():
            raise KeyError(result_id)
        try:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._select_record(connection, result_id)
                if current is None:
                    raise KeyError(result_id)
                if not current.metadata_present:
                    connection.execute(
                        """
                        INSERT INTO result_artifact_metadata
                        (result_id, payload_hash, label, notes, persisted_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            result_id,
                            current.metadata.payload_hash,
                            label if update_label else None,
                            notes if update_notes else None,
                            None,
                        ),
                    )
                else:
                    assignments: list[str] = []
                    values: list[object] = []
                    if update_label:
                        assignments.append("label = ?")
                        values.append(label)
                    if update_notes:
                        assignments.append("notes = ?")
                        values.append(notes)
                    if assignments:
                        values.append(result_id)
                        connection.execute(
                            "UPDATE result_artifact_metadata SET "
                            + ", ".join(assignments)
                            + " WHERE result_id = ?",
                            values,
                        )
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()
        except KeyError:
            raise
        except sqlite3.Error as exc:
            raise ResultArtifactIndexError("mutable metadata update 失敗") from exc
        record = self.get_index(result_id)
        if record is None:
            raise ResultArtifactIndexError("metadata update 後找不到 index")
        return record
