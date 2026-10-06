"""明示市場 CSV plan 的 Windows 隔離 consumer；不掃描、開庫或分享。"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import stat
import uuid
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Mapping

from app_module.personal_data_paths import (
    MarketOnlyExportPlan,
    PersonalDataPathError,
    _absolute,
    _file_identity,
)

RECEIPT_NAME = "market-csv-export.v1.json"
_CHUNK_SIZE = 1024 * 1024
_PRIVATE_PARTS = frozenset({"personal", "output", "sqlite", "watchlists", "research_notes", "ledgers"})
_SQLITE_MAGIC = b"SQLite format 3\x00"
_SQLITE_SIDECAR_MAGIC = (b"\x37\x7f\x06\x82", b"\x37\x7f\x06\x83", b"\xd9\xd5\x05\xf9\x20\xa1\x63\xd7")


class MarketCsvExportError(PersonalDataPathError):
    """具名 consumer 拒絕；失敗目標保留，不能當作完成包。"""


class MarketCsvExportCancelled(MarketCsvExportError):
    """合作取消，不發布完成收據。"""


@dataclass(frozen=True)
class ExportedMarketCsv:
    relative_path: str
    source_identity: tuple[int, int, int, int, int]
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class MarketCsvExportReceipt:
    destination_root: Path
    receipt_path: Path
    receipt_sha256: str
    files: tuple[ExportedMarketCsv, ...]


def _check_cancel(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise MarketCsvExportCancelled("export_cancelled")


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise MarketCsvExportError("export_handle_alias")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _win_handle(path: Path, *, access: int, share: int, creation: int = 3) -> int:
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    handle = create(str(path), access, share, None, creation, 0x02200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    return int(handle)


def _close_handle(handle: int) -> None:
    from ctypes import wintypes

    close = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    close(handle)


def _open_file(path: Path, *, writable: bool = False, renameable: bool = False) -> BinaryIO:
    import msvcrt

    # 不分享 write，來源與輸出都不能在核驗期間被其他 writer 改寫。
    access = (0xC0000000 if writable else 0x80000000) | (0x10000 if renameable else 0)
    handle = _win_handle(path, access=access,
                         share=5 if renameable else 1, creation=1 if writable else 3)
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_BINARY | (os.O_RDWR if writable else os.O_RDONLY))
    except BaseException:
        _close_handle(handle)
        raise
    return os.fdopen(fd, "w+b" if writable else "rb")


class _DirectoryPins:
    def __init__(self, stack: ExitStack) -> None:
        self.stack = stack
        self.identities: dict[Path, tuple[int, int]] = {}

    def pin(self, directory: Path) -> None:
        # 先鎖祖先，再向下開啟；不允許 delete／write sharing，包含 junction 重指向。
        for path in reversed((directory, *directory.parents)):
            if path in self.identities:
                continue
            _absolute(path)
            handle = _win_handle(path, access=0x80, share=1)
            self.stack.callback(_close_handle, handle)
            _absolute(path)
            info = path.stat()
            if not stat.S_ISDIR(info.st_mode):
                raise MarketCsvExportError("export_directory_required", path)
            self.identities[path] = (info.st_dev, info.st_ino)

    def validate(self) -> None:
        for path, expected in self.identities.items():
            _absolute(path)
            info = path.stat()
            if (info.st_dev, info.st_ino) != expected:
                raise MarketCsvExportError("export_directory_changed", path)

    def create(self, directory: Path) -> None:
        if directory in self.identities:
            return
        if directory.parent not in self.identities:
            self.create(directory.parent)
        _absolute(directory)
        directory.mkdir(exist_ok=False)
        self.pin(directory)


def _hash_file(stream: BinaryIO, cancelled: Callable[[], bool] | None) -> str:
    stream.seek(0)
    digest = hashlib.sha256()
    first = True
    while True:
        _check_cancel(cancelled)
        block = stream.read(_CHUNK_SIZE)
        if not block:
            break
        if first and block.startswith((_SQLITE_MAGIC, *_SQLITE_SIDECAR_MAGIC)):
            raise MarketCsvExportError("sqlite_content_excluded")
        if b"\x00" in block:
            raise MarketCsvExportError("binary_csv_content_excluded")
        first = False
        digest.update(block)
    return digest.hexdigest()


def _publish_receipt(stream: BinaryIO, receipt: Path) -> None:
    import msvcrt
    from ctypes import wintypes

    name = str(receipt)
    encoded_name = name.encode("utf-16-le")
    class RenameInfo(ctypes.Structure):
        _fields_ = [("ReplaceIfExists", wintypes.BOOLEAN), ("RootDirectory", wintypes.HANDLE),
                    ("FileNameLength", wintypes.DWORD), ("FileName", wintypes.WCHAR * (len(encoded_name) // 2 + 1))]

    info = RenameInfo()
    info.ReplaceIfExists = False
    info.FileNameLength = len(encoded_name)
    # Win32 FileName 是 NUL 結尾的寬字串；長度欄不含結尾。
    ctypes.memmove(ctypes.addressof(info) + RenameInfo.FileName.offset,
                   encoded_name + b"\x00\x00", len(encoded_name) + 2)
    rename = ctypes.WinDLL("kernel32", use_last_error=True).SetFileInformationByHandle
    rename.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    rename.restype = wintypes.BOOL
    # 依原 handle 原子 rename，不重新開 pending path；不覆寫任何既有收據。
    if not rename(msvcrt.get_osfhandle(stream.fileno()), 3, ctypes.byref(info), ctypes.sizeof(info)):
        raise ctypes.WinError(ctypes.get_last_error())


def export_market_csv(
    plan: MarketOnlyExportPlan,
    *,
    expected_sha256: Mapping[str, str],
    cancelled: Callable[[], bool] | None = None,
) -> MarketCsvExportReceipt:
    """只複製 plan 明列 CSV 至全新隔離目標，最後原子發布收據。

    caller 必須明示與 plan 完全同鍵的接受 SHA-256，不能自動接受目前來源。
    目標父目錄必須已存在；失敗／取消保留 partial，重試要指定另一新目標。
    Windows handle sharing 為本版本必要 backend；其他平台 fail closed。
    CSV 的內容語意、來源授權與分享資格仍須 caller 另行核驗。
    """
    if os.name != "nt":
        raise MarketCsvExportError("export_platform_unsupported")
    if type(plan) is not MarketOnlyExportPlan:
        raise MarketCsvExportError("explicit_market_plan_required")
    _check_cancel(cancelled)
    plan.validate()
    if not plan.files:
        raise MarketCsvExportError("empty_market_export_plan")
    hashes = dict(expected_sha256)
    if set(hashes) != {entry.relative_path for entry in plan.files} or any(
        not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
        for value in hashes.values()
    ):
        raise MarketCsvExportError("explicit_source_hashes_required")
    destination = _absolute(plan.destination_root)
    if destination.exists():
        raise MarketCsvExportError("export_destination_exists", destination)
    if not destination.parent.is_dir():
        raise MarketCsvExportError("export_parent_missing", destination.parent)
    for entry in plan.files:
        parts = Path(entry.relative_path).parts
        if any(part.casefold() in _PRIVATE_PARTS for part in parts):
            raise MarketCsvExportError("private_export_component", entry.relative_path)
        if any(token in parts[-1].casefold() for token in (".sqlite", ".db", "-wal", "-shm", "-journal")):
            raise MarketCsvExportError("sqlite_name_excluded", entry.relative_path)

    try:
        with ExitStack() as stack:
            pins = _DirectoryPins(stack)
            pins.pin(destination.parent)
            sources: list[BinaryIO] = []
            verified: list[ExportedMarketCsv] = []
            for entry in plan.files:
                _check_cancel(cancelled)
                pins.pin(entry.source_path.parent)
                source = stack.enter_context(_open_file(entry.source_path))
                if _identity(os.fstat(source.fileno())) != entry.identity:
                    raise MarketCsvExportError("export_source_identity_changed", entry.source_path)
                digest = _hash_file(source, cancelled)
                if digest != hashes[entry.relative_path]:
                    raise MarketCsvExportError("export_source_hash_mismatch", entry.relative_path)
                if _file_identity(entry.source_path) != entry.identity:
                    raise MarketCsvExportError("export_source_identity_changed", entry.source_path)
                sources.append(source)
                verified.append(ExportedMarketCsv(entry.relative_path, entry.identity, entry.identity[2], digest))
            plan.validate()
            pins.validate()
            _check_cancel(cancelled)
            pins.create(destination)
            outputs: list[BinaryIO] = []
            for entry, source, expected in zip(plan.files, sources, verified):
                _check_cancel(cancelled)
                target = destination / entry.relative_path
                pins.create(target.parent)
                _absolute(target)
                output = stack.enter_context(_open_file(target, writable=True))
                outputs.append(output)
                source.seek(0)
                while True:
                    _check_cancel(cancelled)
                    block = source.read(_CHUNK_SIZE)
                    if not block:
                        break
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())
                if _hash_file(output, cancelled) != expected.sha256:
                    raise MarketCsvExportError("export_copy_hash_mismatch", target)

            # 所有來源與輸出 handle 保留到 commit point；沒有成功收據的 partial 不是完成包。
            for entry, source, output, expected in zip(plan.files, sources, outputs, verified):
                if _identity(os.fstat(source.fileno())) != entry.identity or _file_identity(entry.source_path) != entry.identity:
                    raise MarketCsvExportError("export_source_identity_changed", entry.source_path)
                if _hash_file(source, cancelled) != expected.sha256 or _hash_file(output, cancelled) != expected.sha256:
                    raise MarketCsvExportError("export_final_hash_mismatch", entry.relative_path)
                if _identity(os.fstat(output.fileno())) != _file_identity(destination / entry.relative_path):
                    raise MarketCsvExportError("export_output_identity_changed", entry.relative_path)
            plan.validate()
            pins.validate()
            # pending 內容只宣告核驗；完成資格取決於最後的 canonical filename 原子發布。
            payload = {"schema": "market-csv-export.v1", "status": "verified", "file_count": len(verified),
                       "files": [{"relative_path": f.relative_path, "source_identity": list(f.source_identity),
                                  "size_bytes": f.size_bytes, "sha256": f.sha256} for f in verified]}
            raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            pending = destination / f".market-csv-receipt.{uuid.uuid4().hex}.pending"
            receipt = destination / RECEIPT_NAME
            with _open_file(pending, writable=True, renameable=True) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
                if _identity(os.fstat(stream.fileno())) != _file_identity(pending):
                    raise MarketCsvExportError("export_receipt_identity_changed", pending)
                if _hash_file(stream, cancelled) != hashlib.sha256(raw).hexdigest():
                    raise MarketCsvExportError("export_receipt_hash_mismatch", pending)
                _check_cancel(cancelled)
                # 最後一次 caller callback 之後再核驗；callback 自身也可能改動路徑。
                plan.validate()
                if _identity(os.fstat(stream.fileno())) != _file_identity(pending):
                    raise MarketCsvExportError("export_receipt_identity_changed", pending)
                for entry, source, output, expected in zip(plan.files, sources, outputs, verified):
                    if _identity(os.fstat(source.fileno())) != entry.identity:
                        raise MarketCsvExportError("export_source_identity_changed", entry.source_path)
                    if _hash_file(source, None) != expected.sha256 or _hash_file(output, None) != expected.sha256:
                        raise MarketCsvExportError("export_final_hash_mismatch", entry.relative_path)
                    if _identity(os.fstat(output.fileno())) != _file_identity(destination / entry.relative_path):
                        raise MarketCsvExportError("export_output_identity_changed", entry.relative_path)
                allowed = {destination / entry.relative_path for entry in plan.files} | {pending}
                allowed.update(path for path in pins.identities if path.is_relative_to(destination))
                for directory in pins.identities:
                    if directory.is_relative_to(destination):
                        for child in directory.iterdir():
                            if child not in allowed:
                                raise MarketCsvExportError("unexpected_export_artifact", child)
                pins.validate()
                _publish_receipt(stream, receipt)
                # 發布API成功不足以宣稱完成：核對 exact canonical 路徑的原handle與bytes。
                if pending.exists() or not receipt.exists() or _identity(os.fstat(stream.fileno())) != _file_identity(receipt):
                    raise MarketCsvExportError("export_receipt_publication_mismatch", receipt)
                if _hash_file(stream, None) != hashlib.sha256(raw).hexdigest():
                    raise MarketCsvExportError("export_receipt_hash_mismatch", receipt)
            return MarketCsvExportReceipt(destination, receipt, hashlib.sha256(raw).hexdigest(), tuple(verified))
    except OSError as exc:
        raise MarketCsvExportError("export_io_failed", destination) from exc
