"""儲存位置與明示 Trial／套件根的唯讀、有界盤點。"""

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import stat
from typing import Callable, Mapping


@dataclass(frozen=True)
class StorageLocation:
    name: str
    path: str
    total_bytes: int | None
    free_bytes: int | None
    status: str


@dataclass(frozen=True)
class StorageArtifact:
    name: str
    measured_bytes: int
    complete: bool
    status: str


@dataclass(frozen=True)
class StorageOverview:
    locations: tuple[StorageLocation, ...]
    artifacts: tuple[StorageArtifact, ...]
    limited: bool
    inventory_path: str | None = None
    inventory_status: str = "未提供盤點位置"
    inventory_available: bool = False


def _is_reparse(path: Path, metadata: os.stat_result) -> bool:
    return path.is_symlink() or bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def inspect_storage(
    roots: Mapping[str, Path],
    trial_root: Path | None,
    *,
    package_root: Path | None = None,
    cancel_callback: Callable[[], object] | None = None,
) -> StorageOverview:
    """只查容量根及單一明示盤點根；不遞迴私人資料或跟隨內層連結。"""
    def check_cancel() -> None:
        if cancel_callback is not None and cancel_callback():
            raise ValueError("儲存盤點已取消")

    locations: list[StorageLocation] = []
    for name, path in roots.items():
        check_cancel()
        try:
            if not path.exists():
                raise OSError("路徑不存在")
            disk = shutil.disk_usage(path)
            locations.append(StorageLocation(name, str(path), disk.total, disk.free, "可讀；容量屬整個磁碟"))
        except OSError as exc:
            locations.append(StorageLocation(name, str(path), None, None, str(exc)))

    if package_root is not None and trial_root is not None:
        raise ValueError("package_root 與 trial_root 不可同時指定")
    requested = package_root if package_root is not None else trial_root
    kind = "套件根" if package_root is not None else "Trial 根"
    if requested is None:
        return StorageOverview(tuple(locations), (), False, None, "未提供盤點根；未執行盤點", False)

    requested_path = Path(requested)
    requested_text = str(requested_path)
    artifacts: list[StorageArtifact] = []
    limited = False
    skipped_root_entries = False
    remaining = 4096
    try:
        check_cancel()
        # 明示根可本身是 dist junction；只解析根，不跟隨根以下的連結。
        inventory_root = requested_path.resolve(strict=True)
        if not inventory_root.is_dir():
            return StorageOverview(tuple(locations), (), False, requested_text,
                                   f"{kind}不是目錄；未執行盤點：{requested_text}", False)
        root_info = inventory_root.stat()
        if _is_reparse(inventory_root, root_info):
            return StorageOverview(tuple(locations), (), False, requested_text,
                                   f"{kind}根為連結／重解析點；拒絕盤點：{requested_text}", False)
        # 先確認根目錄本身可列舉，避免把根權限錯誤包裝成成功的空清單。
        check_cancel()
        with os.scandir(inventory_root):
            pass
    except FileNotFoundError as exc:
        return StorageOverview(tuple(locations), (), False, requested_text,
                               f"{kind}未找到；未執行盤點：{requested_text}（{exc}）", False)
    except OSError as exc:
        return StorageOverview(tuple(locations), (), False, requested_text,
                               f"{kind}不可用；未執行盤點：{requested_text}（{exc}）", False)

    def measure_tree(root: Path, *, include_root_files: bool) -> tuple[int, bool, str]:
        nonlocal remaining, limited
        size = 0
        complete = True
        reason = "已量測；引用與保留狀態尚未核對"
        pending = [root]
        while pending:
            check_cancel()
            current = pending.pop()
            try:
                with os.scandir(current) as children:
                    for child in children:
                        check_cancel()
                        if remaining <= 0:
                            limited = True
                            complete = False
                            reason = "達4096項共用盤點上限；大小不完整，保留"
                            return size, complete, reason
                        remaining -= 1
                        path = Path(child.path)
                        try:
                            metadata = child.stat(follow_symlinks=False)
                        except OSError:
                            complete = False
                            reason = "部分項目不可讀；大小不完整，保留"
                            continue
                        if _is_reparse(path, metadata):
                            complete = False
                            reason = "含連結／重解析點；未跟隨，大小不完整，保留"
                        elif stat.S_ISDIR(metadata.st_mode):
                            pending.append(path)
                        elif stat.S_ISREG(metadata.st_mode):
                            # 套件根本身作單一 Artifact，根層檔案亦計入大小。
                            if include_root_files or current != root:
                                size += metadata.st_size
            except OSError:
                complete = False
                reason = "目錄不可讀；大小不完整，保留"
        return size, complete, reason

    if package_root is not None:
        size, complete, reason = measure_tree(inventory_root, include_root_files=True)
        artifacts.append(StorageArtifact(inventory_root.name, size, complete, reason))
    else:
        try:
            with os.scandir(inventory_root) as entries:
                for entry in entries:
                    check_cancel()
                    if remaining <= 0 or len(artifacts) >= 64:
                        limited = True
                        break
                    remaining -= 1
                    path = Path(entry.path)
                    try:
                        metadata = entry.stat(follow_symlinks=False)
                    except OSError:
                        skipped_root_entries = True
                        continue
                    if _is_reparse(path, metadata):
                        skipped_root_entries = True
                        continue
                    if not stat.S_ISDIR(metadata.st_mode):
                        continue
                    size, complete, reason = measure_tree(path, include_root_files=True)
                    artifacts.append(StorageArtifact(path.name, size, complete, reason))
        except OSError as exc:
            return StorageOverview(tuple(locations), (), False, requested_text,
                                   f"{kind}不可讀；未完成盤點：{requested_text}（{exc}）", False)

    status = f"{kind}有界盤點完成"
    if limited:
        status += "；已達64版本或4096項上限，清單／大小未必完整"
    elif skipped_root_entries:
        status += "；部分根層連結或不可讀項目未跟隨／檢查"
    elif any(not item.complete for item in artifacts):
        status += "；含不可讀或未跟隨連結項，大小不完整"
    return StorageOverview(tuple(locations), tuple(artifacts), limited, requested_text, status, True)
