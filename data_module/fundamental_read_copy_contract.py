"""基本面 SQLite 隔離副本的型別化連線契約。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Callable, Literal, Sequence


FUNDAMENTAL_READ_SNAPSHOT_SCHEMA: Literal["selection-fundamental-read-snapshot.v1"] = (
    "selection-fundamental-read-snapshot.v1"
)
FUNDAMENTAL_READ_COPY_BINDING_SCHEMA: Literal[
    "selection-fundamental-read-copy-binding.v1"
] = "selection-fundamental-read-copy-binding.v1"
MAX_COPY_FILE_BYTES = 16 * 1024 * 1024 * 1024
MAX_COPY_MANIFEST_BYTES = 256 * 1024
COPY_HASH_CHUNK_BYTES = 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_REPARSE_POINT = 0x400
_FILE_ROLES = (
    "sqlite_main",
    "sqlite_wal",
    "sqlite_shm",
    "sqlite_rollback_journal",
)


class FundamentalReadCopyBindingError(ValueError):
    """隔離副本、manifest 或檔案 pins 不符合連線契約。"""


class FundamentalReadCopyBindingCancelled(FundamentalReadCopyBindingError):
    """驗證隔離副本時收到取消。"""


@dataclass(frozen=True, slots=True)
class FundamentalReadCopyFilePin:
    """一般檔案的 stat 與內容 hash 證據。"""

    role: str
    path: str
    present: bool
    device: int | None
    inode: int | None
    size_bytes: int | None
    mtime_ns: int | None
    mode: int | None
    sha256: str | None

    def __post_init__(self) -> None:
        if type(self.role) is not str or not self.role:
            raise ValueError("file pin role 必須是非空字串")
        if type(self.path) is not str or not Path(self.path).is_absolute():
            raise ValueError("file pin path 必須是絕對路徑")
        if type(self.present) is not bool:
            raise TypeError("file pin present 必須是 bool")
        values = (self.device, self.inode, self.size_bytes, self.mtime_ns, self.mode)
        if self.present:
            if any(type(value) is not int or value < 0 for value in values):
                raise ValueError("存在檔案的 stat pin 欄位必須是非負整數")
            if type(self.sha256) is not str or not _SHA256_RE.fullmatch(self.sha256):
                raise ValueError("存在檔案必須有 SHA-256")
        elif any(value is not None for value in values) or self.sha256 is not None:
            raise ValueError("不存在檔案不可攜帶 stat 或 SHA-256")

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "path": self.path,
            "present": self.present,
            "device": self.device,
            "inode": self.inode,
            "size_bytes": self.size_bytes,
            "mtime_ns": self.mtime_ns,
            "mode": self.mode,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class FundamentalReadCopyFileReference:
    """snapshot 根下以 POSIX 相對路徑保存的副本檔案。"""

    role: str
    relative_path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if type(self.role) is not str or self.role not in _FILE_ROLES:
            raise ValueError("copy reference role 不支援")
        if type(self.relative_path) is not str or not self.relative_path:
            raise ValueError("copy reference path 必須是非空字串")
        if "\\" in self.relative_path or ":" in self.relative_path:
            raise ValueError("copy reference 必須是 POSIX 相對路徑")
        path = PurePosixPath(self.relative_path)
        if (
            path.is_absolute()
            or str(path) != self.relative_path
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("copy reference 不可離開 snapshot 根目錄")
        if type(self.size_bytes) is not int or self.size_bytes < 0:
            raise ValueError("copy reference size 必須是非負整數")
        if type(self.sha256) is not str or not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError("copy reference SHA-256 格式錯誤")

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class FundamentalReadCopyBinding:
    """將原來源 pins、capture manifest 與實際 reader copy 綁成可驗證入口。"""

    snapshot_id: str
    snapshot_root: str
    source_database_path: str
    reader_database_path: str
    source_file_pins: tuple[FundamentalReadCopyFilePin, ...]
    captured_files: tuple[FundamentalReadCopyFileReference, ...]
    reader_files: tuple[FundamentalReadCopyFileReference, ...]
    capture_manifest_pin: FundamentalReadCopyFilePin
    reader_file_pins_before_open: tuple[FundamentalReadCopyFilePin, ...]
    sqlite_journal_mode: Literal["rollback", "wal"]
    wal_sidecar_state: Literal["complete", "absent", "not_applicable"]
    source_snapshot_sha256: str
    source_copy_bytes: int
    schema_version: Literal["selection-fundamental-read-copy-binding.v1"] = (
        FUNDAMENTAL_READ_COPY_BINDING_SCHEMA
    )

    def __post_init__(self) -> None:
        if type(self.snapshot_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", self.snapshot_id):
            raise ValueError("snapshot_id 格式錯誤")
        for name in ("snapshot_root", "source_database_path", "reader_database_path"):
            value = getattr(self, name)
            if type(value) is not str or not Path(value).is_absolute():
                raise ValueError(f"{name} 必須是絕對路徑")
        if self.schema_version != FUNDAMENTAL_READ_COPY_BINDING_SCHEMA:
            raise ValueError("copy binding schema 不支援")
        if type(self.source_file_pins) is not tuple or tuple(
            pin.role for pin in self.source_file_pins
        ) != _FILE_ROLES:
            raise ValueError("source file pins 必須包含完整有序 SQLite 檔案集合")
        if any(type(pin) is not FundamentalReadCopyFilePin for pin in self.source_file_pins):
            raise TypeError("source file pin 型別錯誤")
        if any(type(item) is not FundamentalReadCopyFileReference for item in (
            *self.captured_files,
            *self.reader_files,
        )):
            raise TypeError("copy reference 型別錯誤")
        if type(self.capture_manifest_pin) is not FundamentalReadCopyFilePin:
            raise TypeError("capture manifest pin 型別錯誤")
        if type(self.reader_file_pins_before_open) is not tuple or tuple(
            pin.role for pin in self.reader_file_pins_before_open
        ) != _FILE_ROLES:
            raise ValueError("reader pins 必須包含完整有序 SQLite 檔案集合")
        if any(
            type(pin) is not FundamentalReadCopyFilePin
            for pin in self.reader_file_pins_before_open
        ):
            raise TypeError("reader file pin 型別錯誤")
        if type(self.source_snapshot_sha256) is not str or not _SHA256_RE.fullmatch(
            self.source_snapshot_sha256
        ):
            raise ValueError("source snapshot SHA-256 格式錯誤")
        if type(self.source_copy_bytes) is not int or self.source_copy_bytes < 0:
            raise ValueError("source_copy_bytes 必須是非負整數")
        if self.sqlite_journal_mode == "wal":
            if self.wal_sidecar_state not in {"complete", "absent"}:
                raise ValueError("WAL sidecar 狀態錯誤")
        elif self.wal_sidecar_state != "not_applicable":
            raise ValueError("rollback journal mode 不可有 WAL sidecar 狀態")

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self._identity_payload())

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "snapshot_root": self.snapshot_root,
            "source_database_path": self.source_database_path,
            "reader_database_path": self.reader_database_path,
            "source_file_pins": [pin.to_dict() for pin in self.source_file_pins],
            "captured_files": [item.to_dict() for item in self.captured_files],
            "reader_files": [item.to_dict() for item in self.reader_files],
            "capture_manifest_pin": self.capture_manifest_pin.to_dict(),
            "reader_file_pins_before_open": [
                pin.to_dict() for pin in self.reader_file_pins_before_open
            ],
            "sqlite_journal_mode": self.sqlite_journal_mode,
            "wal_sidecar_state": self.wal_sidecar_state,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "source_copy_bytes": self.source_copy_bytes,
        }

    def verify_before_open(
        self,
        *,
        database_path: Path | str,
        provider_database_path: Path | str,
        protected_roots: Sequence[Path | str],
        cancel_callback: Callable[[], bool] | None = None,
    ) -> tuple[FundamentalReadCopyFilePin, ...]:
        """重驗確切 reader copy、manifest 與 sidecar，且不開啟 SQLite。"""

        if cancel_callback is not None and not callable(cancel_callback):
            raise TypeError("cancel_callback 必須可呼叫")
        _poll_cancel(cancel_callback)
        root = _canonical_absolute(self.snapshot_root, "snapshot_root")
        source = _canonical_absolute(self.source_database_path, "source_database_path")
        reader = _canonical_absolute(self.reader_database_path, "reader_database_path")
        requested = _canonical_absolute(str(database_path), "database_path")
        provider_path = _canonical_absolute(str(provider_database_path), "provider_database_path")
        if requested != reader or provider_path != reader:
            raise FundamentalReadCopyBindingError("copy binding database path mismatch")
        if _same_path(str(source), str(reader)):
            raise FundamentalReadCopyBindingError("source database and reader copy must differ")
        if root.name.casefold() != self.snapshot_id.casefold():
            raise FundamentalReadCopyBindingError("snapshot root does not match snapshot id")
        if not _same_path(str(reader), str(root / "reader" / Path(source).name)):
            raise FundamentalReadCopyBindingError("reader copy path is outside its snapshot role")
        if _paths_overlap(root, Path(source).parent):
            raise FundamentalReadCopyBindingError("snapshot root overlaps source database root")
        for protected in protected_roots:
            protected_path = Path(os.path.abspath(Path(protected).expanduser()))
            _reject_existing_reparse_components(protected_path)
            if _paths_overlap(root, protected_path):
                raise FundamentalReadCopyBindingError("snapshot root overlaps protected root")

        _reject_reparse_components(Path(source), allow_missing_leaf=True)
        _reject_reparse_components(Path(root))
        _reject_reparse_components(Path(reader))
        manifest_path = root / "snapshot_capture.json"
        if self.capture_manifest_pin.role != "snapshot_capture_manifest" or not _same_path(
            self.capture_manifest_pin.path, str(manifest_path)
        ):
            raise FundamentalReadCopyBindingError("copy binding manifest path mismatch")
        manifest_pin = _pin_file(
            "snapshot_capture_manifest",
            manifest_path,
            required=True,
            max_bytes=MAX_COPY_MANIFEST_BYTES,
            cancel_callback=cancel_callback,
        )
        if manifest_pin != self.capture_manifest_pin:
            raise FundamentalReadCopyBindingError("copy binding manifest pin changed")
        raw_manifest = _read_file_bounded(
            manifest_path,
            max_bytes=MAX_COPY_MANIFEST_BYTES,
            cancel_callback=cancel_callback,
        )
        expected_manifest = self._manifest_payload()
        if raw_manifest != _canonical_json_bytes(expected_manifest):
            raise FundamentalReadCopyBindingError("copy binding manifest bytes mismatch")
        try:
            parsed_manifest = json.loads(
                raw_manifest.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise FundamentalReadCopyBindingError("copy binding manifest invalid") from exc
        if parsed_manifest != expected_manifest:
            raise FundamentalReadCopyBindingError("copy binding manifest payload mismatch")

        self._validate_source_pin_set(Path(source))
        captured_pins = self._validate_references(
            Path(root), "captured", self.captured_files, cancel_callback
        )
        reader_reference_pins = self._validate_references(
            Path(root), "reader", self.reader_files, cancel_callback
        )
        source_pins = tuple(pin for pin in self.source_file_pins if pin.present)
        _require_distinct_copy_files(captured_pins, "captured")
        _require_distinct_copy_files(reader_reference_pins, "reader")
        _require_no_shared_file_identity(source_pins, captured_pins, "source/captured")
        _require_no_shared_file_identity(source_pins, reader_reference_pins, "source/reader")
        _require_no_shared_file_identity(captured_pins, reader_reference_pins, "captured/reader")
        reader_pins = _pin_database_file_set(
            Path(reader),
            cancel_callback=cancel_callback,
        )
        if reader_pins != self.reader_file_pins_before_open:
            raise FundamentalReadCopyBindingError("reader copy pins changed before SQLite open")
        _require_distinct_copy_files(
            tuple(pin for pin in reader_pins if pin.present), "reader database file set"
        )
        _require_no_shared_file_identity(source_pins, reader_pins, "source/reader database")
        _require_no_shared_file_identity(captured_pins, reader_pins, "captured/reader database")
        self._validate_reader_roles(reader_pins)
        _poll_cancel(cancel_callback)
        return reader_pins

    def _validate_source_pin_set(self, source: Path) -> None:
        pins = {pin.role: pin for pin in self.source_file_pins}
        if pins["sqlite_main"].path != str(source) or not pins["sqlite_main"].present:
            raise FundamentalReadCopyBindingError("source main pin mismatch")
        for role, suffix in zip(_FILE_ROLES[1:], ("-wal", "-shm", "-journal"), strict=True):
            if not _same_path(pins[role].path, f"{source}{suffix}"):
                raise FundamentalReadCopyBindingError(f"source {role} path mismatch")
        if pins["sqlite_rollback_journal"].present:
            raise FundamentalReadCopyBindingError("rollback journal source copy is refused")
        if self.sqlite_journal_mode == "rollback":
            if pins["sqlite_wal"].present or pins["sqlite_shm"].present:
                raise FundamentalReadCopyBindingError("rollback source has WAL sidecars")
        elif self.wal_sidecar_state == "complete":
            if not pins["sqlite_wal"].present or not pins["sqlite_shm"].present:
                raise FundamentalReadCopyBindingError("complete WAL source pins are incomplete")
        elif pins["sqlite_wal"].present or pins["sqlite_shm"].present:
            raise FundamentalReadCopyBindingError("absent WAL source pins contain sidecars")
        copy_bytes = sum(pin.size_bytes or 0 for pin in self.source_file_pins if pin.present)
        if copy_bytes != self.source_copy_bytes:
            raise FundamentalReadCopyBindingError("source copy byte count mismatch")
        source_snapshot_sha = _canonical_sha256(
            {
                "schema_version": FUNDAMENTAL_READ_SNAPSHOT_SCHEMA,
                "source_database_path": str(source),
                "source_file_pins": [pin.to_dict() for pin in self.source_file_pins],
                "captured_files": [item.to_dict() for item in self.captured_files],
            }
        )
        if source_snapshot_sha != self.source_snapshot_sha256:
            raise FundamentalReadCopyBindingError("source snapshot identity mismatch")

    def _validate_references(
        self,
        root: Path,
        directory: Literal["captured", "reader"],
        references: tuple[FundamentalReadCopyFileReference, ...],
        cancel_callback: Callable[[], bool] | None,
    ) -> tuple[FundamentalReadCopyFilePin, ...]:
        expected_roles = tuple(pin.role for pin in self.source_file_pins if pin.present)
        if tuple(item.role for item in references) != expected_roles:
            raise FundamentalReadCopyBindingError(f"{directory} copy references incomplete")
        source_by_role = {pin.role: pin for pin in self.source_file_pins}
        verified: list[FundamentalReadCopyFilePin] = []
        for item in references:
            _poll_cancel(cancel_callback)
            expected_relative = f"{directory}/{Path(source_by_role[item.role].path).name}"
            if item.relative_path != expected_relative:
                raise FundamentalReadCopyBindingError(f"{directory} reference path mismatch")
            path = root.joinpath(*PurePosixPath(item.relative_path).parts)
            _reject_reparse_components(path)
            current = _pin_file(
                item.role,
                path,
                required=True,
                max_bytes=MAX_COPY_FILE_BYTES,
                cancel_callback=cancel_callback,
            )
            if (
                current.size_bytes != item.size_bytes
                or current.sha256 != item.sha256
                or item.size_bytes != source_by_role[item.role].size_bytes
                or item.sha256 != source_by_role[item.role].sha256
            ):
                raise FundamentalReadCopyBindingError(f"{directory} copy bytes mismatch:{item.role}")
            verified.append(current)
        return tuple(verified)

    def _validate_reader_roles(
        self,
        reader_pins: tuple[FundamentalReadCopyFilePin, ...],
    ) -> None:
        by_role = {pin.role: pin for pin in reader_pins}
        if by_role["sqlite_rollback_journal"].present:
            raise FundamentalReadCopyBindingError("reader rollback journal is refused")
        reader_refs = {item.role: item for item in self.reader_files}
        for role in ("sqlite_main", "sqlite_wal", "sqlite_shm"):
            pin = by_role[role]
            ref = reader_refs.get(role)
            if ref is not None:
                if not pin.present or pin.size_bytes != ref.size_bytes or pin.sha256 != ref.sha256:
                    raise FundamentalReadCopyBindingError(f"reader reference pin mismatch:{role}")
            elif pin.present and not (
                self.sqlite_journal_mode == "wal" and self.wal_sidecar_state == "absent"
                and role in {"sqlite_wal", "sqlite_shm"}
            ):
                raise FundamentalReadCopyBindingError(f"unexpected reader sidecar:{role}")
        if not by_role["sqlite_main"].present:
            raise FundamentalReadCopyBindingError("reader main copy is missing")
        if self.wal_sidecar_state == "complete":
            if not by_role["sqlite_wal"].present or not by_role["sqlite_shm"].present:
                raise FundamentalReadCopyBindingError("reader WAL sidecars are incomplete")

    def _manifest_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": FUNDAMENTAL_READ_SNAPSHOT_SCHEMA,
            "snapshot_id": self.snapshot_id,
            "source_database_path": self.source_database_path,
            "source_file_pins_start": [pin.to_dict() for pin in self.source_file_pins],
            "captured_files": [item.to_dict() for item in self.captured_files],
            "reader_files_before_sqlite_open": [item.to_dict() for item in self.reader_files],
            "sqlite_journal_mode": self.sqlite_journal_mode,
            "wal_sidecar_state": self.wal_sidecar_state,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "source_copy_bytes": self.source_copy_bytes,
            "duplicated_disk_bytes": self.source_copy_bytes * 2,
            "manifest_state": "captured_source_copy",
        }
        payload["manifest_sha256"] = _canonical_sha256(payload)
        return payload


def _pin_database_file_set(
    database_path: Path,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> tuple[FundamentalReadCopyFilePin, ...]:
    pins: list[FundamentalReadCopyFilePin] = []
    for role, suffix, required in (
        ("sqlite_main", "", True),
        ("sqlite_wal", "-wal", False),
        ("sqlite_shm", "-shm", False),
        ("sqlite_rollback_journal", "-journal", False),
    ):
        _poll_cancel(cancel_callback)
        path = database_path if not suffix else Path(f"{database_path}{suffix}")
        pins.append(
            _pin_file(
                role,
                path,
                required=required,
                max_bytes=MAX_COPY_FILE_BYTES,
                cancel_callback=cancel_callback,
            )
        )
    return tuple(pins)


def _pin_file(
    role: str,
    path: Path,
    *,
    required: bool,
    max_bytes: int,
    cancel_callback: Callable[[], bool] | None,
) -> FundamentalReadCopyFilePin:
    _reject_reparse_components(path, allow_missing_leaf=not required)
    absolute = Path(os.path.abspath(path))
    try:
        first = path.lstat()
    except FileNotFoundError:
        if required:
            raise FundamentalReadCopyBindingError(f"required copy file is missing:{role}")
        return FundamentalReadCopyFilePin(role, str(absolute), False, None, None, None, None, None, None)
    _require_regular(path, first, role)
    _require_single_link(first, role)
    if first.st_size < 0 or first.st_size > max_bytes:
        raise FundamentalReadCopyBindingError(f"copy file exceeds bounded size:{role}")
    digest = sha256()
    total = 0
    try:
        with path.open("rb") as stream:
            while True:
                _poll_cancel(cancel_callback)
                block = stream.read(COPY_HASH_CHUNK_BYTES)
                if not block:
                    break
                total += len(block)
                if total > max_bytes:
                    raise FundamentalReadCopyBindingError(f"copy file exceeds bounded size:{role}")
                digest.update(block)
                _poll_cancel(cancel_callback)
    except FundamentalReadCopyBindingCancelled:
        raise
    except OSError as exc:
        raise FundamentalReadCopyBindingError(
            f"copy file hash failed:{role}:{type(exc).__name__}"
        ) from exc
    second = path.lstat()
    _require_regular(path, second, role)
    _require_single_link(second, role)
    if _stat_identity(first) != _stat_identity(second) or total != first.st_size:
        raise FundamentalReadCopyBindingError(f"copy file changed while hashing:{role}")
    return FundamentalReadCopyFilePin(
        role=role,
        path=str(absolute),
        present=True,
        device=int(second.st_dev),
        inode=int(second.st_ino),
        size_bytes=int(second.st_size),
        mtime_ns=int(second.st_mtime_ns),
        mode=int(stat.S_IMODE(second.st_mode)),
        sha256=digest.hexdigest(),
    )


def _read_file_bounded(
    path: Path,
    *,
    max_bytes: int,
    cancel_callback: Callable[[], bool] | None,
) -> bytes:
    _poll_cancel(cancel_callback)
    before = path.lstat()
    _require_regular(path, before, "copy_manifest")
    if before.st_size > max_bytes:
        raise FundamentalReadCopyBindingError("copy manifest exceeds size bound")
    output = bytearray()
    try:
        with path.open("rb") as stream:
            while True:
                _poll_cancel(cancel_callback)
                block = stream.read(min(COPY_HASH_CHUNK_BYTES, max_bytes + 1 - len(output)))
                if not block:
                    break
                output.extend(block)
                if len(output) > max_bytes:
                    raise FundamentalReadCopyBindingError("copy manifest exceeds size bound")
                _poll_cancel(cancel_callback)
    except FundamentalReadCopyBindingCancelled:
        raise
    except OSError as exc:
        raise FundamentalReadCopyBindingError(
            f"copy manifest read failed:{type(exc).__name__}"
        ) from exc
    after = path.lstat()
    _require_regular(path, after, "copy_manifest")
    if _stat_identity(before) != _stat_identity(after):
        raise FundamentalReadCopyBindingError("copy manifest changed while reading")
    return bytes(output)


def _reject_reparse_components(path: Path, *, allow_missing_leaf: bool = False) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    parts = absolute.parts[1:]
    for index, part in enumerate(parts):
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if allow_missing_leaf and index == len(parts) - 1:
                return
            raise FundamentalReadCopyBindingError("copy path component is missing")
        attributes = int(getattr(metadata, "st_file_attributes", 0))
        if stat.S_ISLNK(metadata.st_mode) or attributes & _WINDOWS_REPARSE_POINT:
            raise FundamentalReadCopyBindingError("copy path contains a reparse point")


def _reject_existing_reparse_components(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return
        attributes = int(getattr(metadata, "st_file_attributes", 0))
        if stat.S_ISLNK(metadata.st_mode) or attributes & _WINDOWS_REPARSE_POINT:
            raise FundamentalReadCopyBindingError("protected root contains a reparse point")


def _require_regular(path: Path, metadata: os.stat_result, role: str) -> None:
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    if stat.S_ISLNK(metadata.st_mode) or attributes & _WINDOWS_REPARSE_POINT:
        raise FundamentalReadCopyBindingError(f"copy path is a reparse point:{role}")
    if not stat.S_ISREG(metadata.st_mode):
        raise FundamentalReadCopyBindingError(f"copy path is not a regular file:{role}")


def _require_single_link(metadata: os.stat_result, role: str) -> None:
    link_count = getattr(metadata, "st_nlink", None)
    if type(link_count) is not int or link_count != 1:
        raise FundamentalReadCopyBindingError(f"copy file must have exactly one hard link:{role}")


def _physical_identity(pin: FundamentalReadCopyFilePin) -> tuple[int, int] | None:
    if not pin.present:
        return None
    if pin.device is None or pin.inode is None:
        raise FundamentalReadCopyBindingError("present copy file has no physical identity")
    return int(pin.device), int(pin.inode)


def _require_distinct_copy_files(
    pins: Sequence[FundamentalReadCopyFilePin],
    label: str,
) -> None:
    seen: set[tuple[int, int]] = set()
    for pin in pins:
        identity = _physical_identity(pin)
        if identity is None:
            continue
        if identity in seen:
            raise FundamentalReadCopyBindingError(f"copy files share a physical identity:{label}")
        seen.add(identity)


def _require_no_shared_file_identity(
    left: Sequence[FundamentalReadCopyFilePin],
    right: Sequence[FundamentalReadCopyFilePin],
    label: str,
) -> None:
    left_identities = {
        identity
        for pin in left
        if (identity := _physical_identity(pin)) is not None
    }
    for pin in right:
        identity = _physical_identity(pin)
        if identity is not None and identity in left_identities:
            raise FundamentalReadCopyBindingError(f"copy files share a physical identity:{label}")


def _canonical_absolute(value: str, name: str) -> Path:
    raw = Path(value)
    absolute = Path(os.path.abspath(raw))
    if not raw.is_absolute() or str(raw) != str(absolute):
        raise FundamentalReadCopyBindingError(f"{name} must be canonical absolute path")
    return absolute


def _paths_overlap(left: Path, right: Path) -> bool:
    left = Path(os.path.normcase(os.path.abspath(left)))
    right = Path(os.path.normcase(os.path.abspath(right)))
    try:
        left.relative_to(right)
        return True
    except ValueError:
        pass
    try:
        right.relative_to(left)
        return True
    except ValueError:
        return False


def _same_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def _stat_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_size),
        int(metadata.st_mtime_ns),
        int(stat.S_IMODE(metadata.st_mode)),
    )


def _poll_cancel(callback: Callable[[], bool] | None) -> None:
    if callback is None:
        return
    try:
        value = callback()
    except BaseException as exc:
        raise FundamentalReadCopyBindingCancelled(
            f"copy binding cancel callback failed:{type(exc).__name__}"
        ) from exc
    if type(value) is not bool:
        raise FundamentalReadCopyBindingCancelled("copy binding cancel callback must return bool")
    if value:
        raise FundamentalReadCopyBindingCancelled("copy binding validation cancelled")


def _unique_object(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: object) -> str:
    return sha256(_canonical_json_bytes(value)).hexdigest()
