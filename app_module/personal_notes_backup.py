"""有界、create-only 的私人研究筆記備份與還原 adapter。

此 adapter 保存既有 journal JSONL 位元組，不解讀行情或計算資料。所有輸出路徑
都由 caller 明示；操作前使用 personal store guard，I/O 時使用 Windows path renderer。
路徑所有權與其父目錄由 caller 負責。本模組不宣稱能抵抗惡意並行改寫或目錄替換。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Callable, Mapping

from app_module.personal_data_paths import (
    PersonalDataPaths,
    PersonalDataPathError,
    _absolute,
    to_internal_io_path,
)
from app_module.personal_journal_paths import PersonalJournalPaths
from app_module.personal_store_selection import assert_personal_store_path


PERSONAL_NOTES_BACKUP_SCHEMA_VERSION = "personal-notes-backup.v1"
_READ_CHUNK_BYTES = 64 * 1024
_MAX_RECEIPT_BYTES = 32 * 1024
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class PersonalNotesBackupError(ValueError):
    """備份或還原路徑契約失敗時回報具名錯誤。"""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class PersonalNotesBackupReceipt:
    schema_version: str
    store_identity: str
    source_path: Path
    source_size_bytes: int
    source_sha256: str
    snapshot_path: Path
    snapshot_size_bytes: int
    snapshot_sha256: str
    receipt_path: Path
    receipt_sha256: str
    created: bool


@dataclass(frozen=True)
class PersonalNotesRestoreResult:
    store_identity: str
    receipt_sha256: str
    snapshot_path: Path
    target_path: Path
    size_bytes: int
    snapshot_sha256: str
    restored: bool


@dataclass(frozen=True)
class _LoadedReceipt:
    source_path: Path
    source_size_bytes: int
    source_sha256: str
    snapshot_path: Path
    snapshot_size_bytes: int
    snapshot_sha256: str
    receipt_sha256: str


def _raise_if_cancelled(cancel_check: Callable[[], bool] | None) -> None:
    if cancel_check is not None and cancel_check():
        raise PersonalNotesBackupError("cancelled")


def _guard_personal_file(paths: PersonalDataPaths, path: Path) -> Path:
    try:
        canonical = assert_personal_store_path(paths, path)
    except PersonalDataPathError as exc:
        raise PersonalNotesBackupError(exc.code, str(path)) from exc
    if canonical != path:
        raise PersonalNotesBackupError("canonical_path_required", str(path))
    return canonical


def _guard_personal_directory(paths: PersonalDataPaths, path: Path) -> Path:
    try:
        paths.validate()
        root = _absolute(paths.personal_root)
        canonical = _absolute(path)
    except PersonalDataPathError as exc:
        raise PersonalNotesBackupError(exc.code, str(path)) from exc
    if canonical != path or canonical == root or not canonical.is_relative_to(root):
        raise PersonalNotesBackupError("personal_directory_outside_root", str(path))
    try:
        info = os.stat(to_internal_io_path(canonical), follow_symlinks=False)
    except FileNotFoundError:
        return canonical
    except OSError as exc:
        raise PersonalNotesBackupError("personal_directory_unavailable", str(path)) from exc
    if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise PersonalNotesBackupError("personal_directory_type_or_alias", str(path))
    return canonical


def _lstat_optional(path: Path) -> os.stat_result | None:
    try:
        return os.stat(to_internal_io_path(path), follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PersonalNotesBackupError("path_unavailable", str(path)) from exc


def _regular_single_link(info: os.stat_result, *, code: str) -> None:
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or getattr(info, "st_file_attributes", 0) & 0x400
    ):
        raise PersonalNotesBackupError(code)


def _stat_signature(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
        int(info.st_nlink),
    )


def _read_bounded_personal_file(
    paths: PersonalDataPaths,
    path: Path,
    *,
    max_bytes: int,
    missing_code: str,
    too_large_code: str,
    cancel_check: Callable[[], bool] | None,
) -> bytes:
    canonical = _guard_personal_file(paths, path)
    io_path = to_internal_io_path(canonical)
    before_path = _lstat_optional(canonical)
    if before_path is None:
        raise PersonalNotesBackupError(missing_code, str(path))
    _regular_single_link(before_path, code="personal_file_alias_or_type")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(io_path, flags)
    except OSError as exc:
        raise PersonalNotesBackupError("personal_file_open_failed", str(path)) from exc

    chunks: list[bytes] = []
    size = 0
    try:
        with os.fdopen(fd, "rb") as stream:
            before_handle = os.fstat(stream.fileno())
            _regular_single_link(before_handle, code="personal_file_alias_or_type")
            if _stat_signature(before_path) != _stat_signature(before_handle):
                raise PersonalNotesBackupError("personal_file_changed_before_read", str(path))

            while size <= max_bytes:
                _raise_if_cancelled(cancel_check)
                request_size = min(_READ_CHUNK_BYTES, max_bytes - size + 1)
                chunk = stream.read(request_size)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > max_bytes:
                    break

            after_handle = os.fstat(stream.fileno())
        after_path = _lstat_optional(canonical)
    except PersonalNotesBackupError:
        raise
    except OSError as exc:
        raise PersonalNotesBackupError("personal_file_read_failed", str(path)) from exc

    if after_path is None:
        raise PersonalNotesBackupError("personal_file_changed_during_read", str(path))
    _regular_single_link(after_handle, code="personal_file_alias_or_type")
    _regular_single_link(after_path, code="personal_file_alias_or_type")
    if not (
        _stat_signature(before_path)
        == _stat_signature(before_handle)
        == _stat_signature(after_handle)
        == _stat_signature(after_path)
    ):
        raise PersonalNotesBackupError("personal_file_changed_during_read", str(path))
    if size > max_bytes:
        raise PersonalNotesBackupError(too_large_code, str(path))
    return b"".join(chunks)


def _exclusive_create_write(
    path: Path,
    payload: bytes,
    *,
    cancel_check: Callable[[], bool] | None,
) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(to_internal_io_path(path), flags, 0o600)
    except FileExistsError as exc:
        raise PersonalNotesBackupError("create_only_target_exists", str(path)) from exc
    except OSError as exc:
        raise PersonalNotesBackupError("create_only_open_failed", str(path)) from exc

    try:
        with os.fdopen(fd, "wb") as stream:
            offset = 0
            while offset < len(payload):
                _raise_if_cancelled(cancel_check)
                end = min(offset + _READ_CHUNK_BYTES, len(payload))
                written = stream.write(payload[offset:end])
                if written is None or written <= 0:
                    raise PersonalNotesBackupError("create_only_write_failed", str(path))
                offset += written
            stream.flush()
            os.fsync(stream.fileno())
    except PersonalNotesBackupError:
        raise
    except OSError as exc:
        raise PersonalNotesBackupError("create_only_write_failed", str(path)) from exc


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    text = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (text + "\n").encode("utf-8")


def _valid_sha256(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise PersonalNotesBackupError(code)
    return value


def _valid_size(value: object, max_bytes: int, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= max_bytes:
        raise PersonalNotesBackupError(code)
    return value


class PersonalNotesBackupAdapter:
    """為單一已知 identity 的 `PersonalJournalPaths.journal_file` 備份／還原。

    `backup` 的預設行為是只讀 dry-run，回傳預計 receipt 及其 digest，但不建立目錄或
    輸出檔。正式 create-only 寫入須明確傳 `confirmed=True`。Restore 亦同；target 永遠
    是 `target_journal_paths.journal_file`，不接受任意 destination 檔案。
    """

    def __init__(
        self,
        journal_paths: PersonalJournalPaths,
        *,
        store_identity: str,
        max_bytes: int,
    ) -> None:
        if not isinstance(store_identity, str) or not store_identity.strip():
            raise PersonalNotesBackupError("store_identity_unknown")
        if store_identity != store_identity.strip():
            raise PersonalNotesBackupError("store_identity_not_canonical")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise PersonalNotesBackupError("positive_byte_budget_required")
        self.journal_paths = journal_paths
        self.store_identity = store_identity
        self.max_bytes = max_bytes

    @property
    def _source_path(self) -> Path:
        return self.journal_paths.journal_file

    @property
    def _backup_root(self) -> Path:
        return self.journal_paths.backup_root

    def _guard_backup_child(self, path: Path) -> Path:
        root = _guard_personal_directory(self.journal_paths.personal_paths, self._backup_root)
        if path.parent != root or path == root or path.name in {"", ".", ".."}:
            raise PersonalNotesBackupError("backup_output_must_be_direct_child", str(path))
        canonical = _guard_personal_file(self.journal_paths.personal_paths, path)
        if canonical == self._source_path:
            raise PersonalNotesBackupError("backup_output_aliases_source", str(path))
        return canonical

    def _check_outputs_absent(self, snapshot_path: Path, receipt_path: Path) -> None:
        self._check_output_absent(snapshot_path)
        self._check_output_absent(receipt_path)

    @staticmethod
    def _check_output_absent(path: Path) -> None:
        if _lstat_optional(path) is not None:
            raise PersonalNotesBackupError("backup_output_exists", str(path))

    @staticmethod
    def _check_receipt_budget(manifest: bytes) -> None:
        if len(manifest) > _MAX_RECEIPT_BYTES:
            raise PersonalNotesBackupError("receipt_exceeds_byte_budget")

    def _manifest(
        self,
        *,
        source_path: Path,
        source_bytes: bytes,
        snapshot_path: Path,
        snapshot_bytes: bytes,
    ) -> bytes:
        return _canonical_json(
            {
                "schema_version": PERSONAL_NOTES_BACKUP_SCHEMA_VERSION,
                "store_identity": self.store_identity,
                "source": {
                    "canonical_path": str(source_path),
                    "size_bytes": len(source_bytes),
                    "sha256": _sha256(source_bytes),
                },
                "snapshot": {
                    "canonical_path": str(snapshot_path),
                    "size_bytes": len(snapshot_bytes),
                    "sha256": _sha256(snapshot_bytes),
                },
            }
        )

    def _ensure_backup_root(self) -> None:
        root = _guard_personal_directory(self.journal_paths.personal_paths, self._backup_root)
        Path(to_internal_io_path(root)).mkdir(parents=True, exist_ok=True)
        _guard_personal_directory(self.journal_paths.personal_paths, root)

    def backup(
        self,
        snapshot_path: Path,
        receipt_path: Path,
        *,
        confirmed: bool = False,
        cancel_check: Callable[[], bool] | None = None,
    ) -> PersonalNotesBackupReceipt:
        _raise_if_cancelled(cancel_check)
        source_path = _guard_personal_file(self.journal_paths.personal_paths, self._source_path)
        snapshot = self._guard_backup_child(snapshot_path)
        receipt = self._guard_backup_child(receipt_path)
        if snapshot == receipt:
            raise PersonalNotesBackupError("backup_outputs_must_be_distinct")
        self._check_outputs_absent(snapshot, receipt)

        source_bytes = _read_bounded_personal_file(
            self.journal_paths.personal_paths,
            source_path,
            max_bytes=self.max_bytes,
            missing_code="notes_source_missing",
            too_large_code="notes_source_exceeds_byte_budget",
            cancel_check=cancel_check,
        )
        _raise_if_cancelled(cancel_check)
        manifest = self._manifest(
            source_path=source_path,
            source_bytes=source_bytes,
            snapshot_path=snapshot,
            snapshot_bytes=source_bytes,
        )
        self._check_receipt_budget(manifest)
        manifest_sha256 = _sha256(manifest)

        if confirmed:
            self._ensure_backup_root()
            _raise_if_cancelled(cancel_check)
            guarded_snapshot = self._guard_backup_child(snapshot)
            guarded_receipt = self._guard_backup_child(receipt)
            if guarded_snapshot != snapshot or guarded_receipt != receipt:
                raise PersonalNotesBackupError("backup_output_path_changed")
            self._check_outputs_absent(snapshot, receipt)
            _exclusive_create_write(snapshot, source_bytes, cancel_check=cancel_check)
            snapshot_bytes = _read_bounded_personal_file(
                self.journal_paths.personal_paths,
                snapshot,
                max_bytes=self.max_bytes,
                missing_code="snapshot_missing",
                too_large_code="snapshot_exceeds_byte_budget",
                cancel_check=cancel_check,
            )
            if snapshot_bytes != source_bytes:
                raise PersonalNotesBackupError("snapshot_verification_failed", str(snapshot))
            # Rebuild the receipt after verifying the bytes actually stored in the snapshot.
            manifest = self._manifest(
                source_path=source_path,
                source_bytes=source_bytes,
                snapshot_path=snapshot,
                snapshot_bytes=snapshot_bytes,
            )
            self._check_receipt_budget(manifest)
            manifest_sha256 = _sha256(manifest)
            _raise_if_cancelled(cancel_check)
            guarded_snapshot = self._guard_backup_child(snapshot)
            guarded_receipt = self._guard_backup_child(receipt)
            if guarded_snapshot != snapshot or guarded_receipt != receipt:
                raise PersonalNotesBackupError("backup_output_path_changed")
            self._check_output_absent(receipt)
            _exclusive_create_write(receipt, manifest, cancel_check=cancel_check)
            receipt_readback = _read_bounded_personal_file(
                self.journal_paths.personal_paths,
                receipt,
                max_bytes=_MAX_RECEIPT_BYTES,
                missing_code="receipt_missing",
                too_large_code="receipt_exceeds_byte_budget",
                cancel_check=cancel_check,
            )
            if receipt_readback != manifest or _sha256(receipt_readback) != manifest_sha256:
                raise PersonalNotesBackupError("receipt_verification_failed", str(receipt))

        return PersonalNotesBackupReceipt(
            schema_version=PERSONAL_NOTES_BACKUP_SCHEMA_VERSION,
            store_identity=self.store_identity,
            source_path=source_path,
            source_size_bytes=len(source_bytes),
            source_sha256=_sha256(source_bytes),
            snapshot_path=snapshot,
            snapshot_size_bytes=len(source_bytes),
            snapshot_sha256=_sha256(source_bytes),
            receipt_path=receipt,
            receipt_sha256=manifest_sha256,
            created=confirmed,
        )

    def _load_pinned_receipt(
        self,
        receipt_path: Path,
        *,
        expected_receipt_sha256: str,
        cancel_check: Callable[[], bool] | None,
    ) -> _LoadedReceipt:
        expected_digest = _valid_sha256(
            expected_receipt_sha256.casefold()
            if isinstance(expected_receipt_sha256, str)
            else expected_receipt_sha256,
            "receipt_pin_invalid",
        )
        receipt = self._guard_backup_child(receipt_path)
        receipt_bytes = _read_bounded_personal_file(
            self.journal_paths.personal_paths,
            receipt,
            max_bytes=_MAX_RECEIPT_BYTES,
            missing_code="receipt_missing",
            too_large_code="receipt_exceeds_byte_budget",
            cancel_check=cancel_check,
        )
        digest = _sha256(receipt_bytes)
        if digest != expected_digest:
            raise PersonalNotesBackupError("receipt_pin_mismatch", str(receipt))
        try:
            raw = json.loads(receipt_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PersonalNotesBackupError("receipt_invalid_json", str(receipt)) from exc
        if not isinstance(raw, dict):
            raise PersonalNotesBackupError("receipt_invalid_shape")
        if raw.get("schema_version") != PERSONAL_NOTES_BACKUP_SCHEMA_VERSION:
            raise PersonalNotesBackupError("receipt_schema_unsupported")
        if raw.get("store_identity") != self.store_identity:
            raise PersonalNotesBackupError("receipt_identity_mismatch")

        source = raw.get("source")
        snapshot = raw.get("snapshot")
        if not isinstance(source, dict) or not isinstance(snapshot, dict):
            raise PersonalNotesBackupError("receipt_invalid_shape")
        source_path_raw = source.get("canonical_path")
        snapshot_path_raw = snapshot.get("canonical_path")
        if not isinstance(source_path_raw, str) or not isinstance(snapshot_path_raw, str):
            raise PersonalNotesBackupError("receipt_path_invalid")
        source_path = Path(source_path_raw)
        snapshot_path = Path(snapshot_path_raw)
        expected_source_path = _guard_personal_file(
            self.journal_paths.personal_paths, self._source_path
        )
        if source_path != expected_source_path or str(source_path) != source_path_raw:
            raise PersonalNotesBackupError("receipt_source_path_mismatch")
        guarded_snapshot = self._guard_backup_child(snapshot_path)
        if guarded_snapshot != snapshot_path or str(guarded_snapshot) != snapshot_path_raw:
            raise PersonalNotesBackupError("receipt_snapshot_path_invalid")

        source_size = _valid_size(
            source.get("size_bytes"), self.max_bytes, "receipt_source_size_invalid"
        )
        snapshot_size = _valid_size(
            snapshot.get("size_bytes"), self.max_bytes, "receipt_snapshot_size_invalid"
        )
        source_sha = _valid_sha256(source.get("sha256"), "receipt_source_hash_invalid")
        snapshot_sha = _valid_sha256(snapshot.get("sha256"), "receipt_snapshot_hash_invalid")
        if source_size != snapshot_size or source_sha != snapshot_sha:
            raise PersonalNotesBackupError("receipt_source_snapshot_mismatch")
        return _LoadedReceipt(
            source_path=source_path,
            source_size_bytes=source_size,
            source_sha256=source_sha,
            snapshot_path=snapshot_path,
            snapshot_size_bytes=snapshot_size,
            snapshot_sha256=snapshot_sha,
            receipt_sha256=digest,
        )

    def _ensure_target_parent(self, target: PersonalJournalPaths) -> None:
        parent = target.journal_file.parent
        try:
            self._guard_target_path(target, target.journal_file)
            target.personal_paths.validate()
            canonical_parent = _absolute(parent)
        except PersonalDataPathError as exc:
            raise PersonalNotesBackupError(exc.code, str(parent)) from exc
        if canonical_parent != parent:
            raise PersonalNotesBackupError("target_parent_not_canonical", str(parent))
        Path(to_internal_io_path(canonical_parent)).mkdir(parents=True, exist_ok=True)
        self._guard_target_directory(target, canonical_parent)

    @staticmethod
    def _guard_target_path(target: PersonalJournalPaths, path: Path) -> Path:
        return _guard_personal_file(target.personal_paths, path)

    @staticmethod
    def _guard_target_directory(target: PersonalJournalPaths, path: Path) -> Path:
        return _guard_personal_directory(target.personal_paths, path)

    def restore_into(
        self,
        target_journal_paths: PersonalJournalPaths,
        receipt_path: Path,
        *,
        expected_receipt_sha256: str,
        confirmed: bool = False,
        cancel_check: Callable[[], bool] | None = None,
    ) -> PersonalNotesRestoreResult:
        _raise_if_cancelled(cancel_check)
        loaded = self._load_pinned_receipt(
            receipt_path,
            expected_receipt_sha256=expected_receipt_sha256,
            cancel_check=cancel_check,
        )
        snapshot_bytes = _read_bounded_personal_file(
            self.journal_paths.personal_paths,
            loaded.snapshot_path,
            max_bytes=self.max_bytes,
            missing_code="snapshot_missing",
            too_large_code="snapshot_exceeds_byte_budget",
            cancel_check=cancel_check,
        )
        if len(snapshot_bytes) != loaded.snapshot_size_bytes:
            raise PersonalNotesBackupError("snapshot_size_mismatch", str(loaded.snapshot_path))
        if _sha256(snapshot_bytes) != loaded.snapshot_sha256:
            raise PersonalNotesBackupError("snapshot_hash_mismatch", str(loaded.snapshot_path))

        target = self._guard_target_path(target_journal_paths, target_journal_paths.journal_file)
        existing_target = _lstat_optional(target)
        if existing_target is not None:
            _regular_single_link(existing_target, code="target_alias_or_type")
            raise PersonalNotesBackupError("restore_target_exists", str(target))
        _raise_if_cancelled(cancel_check)

        if confirmed:
            self._ensure_target_parent(target_journal_paths)
            # Recheck after directory creation; the final file is still create-only.
            self._guard_target_path(target_journal_paths, target)
            if _lstat_optional(target) is not None:
                raise PersonalNotesBackupError("restore_target_exists", str(target))
            _exclusive_create_write(target, snapshot_bytes, cancel_check=cancel_check)
            restored_bytes = _read_bounded_personal_file(
                target_journal_paths.personal_paths,
                target,
                max_bytes=self.max_bytes,
                missing_code="restored_target_missing",
                too_large_code="restored_notes_exceed_byte_budget",
                cancel_check=cancel_check,
            )
            if restored_bytes != snapshot_bytes:
                raise PersonalNotesBackupError("restore_verification_failed", str(target))

        return PersonalNotesRestoreResult(
            store_identity=self.store_identity,
            receipt_sha256=loaded.receipt_sha256,
            snapshot_path=loaded.snapshot_path,
            target_path=target,
            size_bytes=len(snapshot_bytes),
            snapshot_sha256=loaded.snapshot_sha256,
            restored=confirmed,
        )
