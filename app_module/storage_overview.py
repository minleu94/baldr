"""儲存位置與 Trial 大小的唯讀、有界盤點；不推定任何檔案可刪除。"""

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


def inspect_storage(
    roots: Mapping[str, Path], trial_root: Path, *,
    cancel_callback: Callable[[], object] | None = None,
) -> StorageOverview:
    """只查 volume 與明示 Trial 根；不遞迴市場資料、模型或私人紀錄。"""
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
    artifacts: list[StorageArtifact] = []
    remaining = 4096
    limited = False
    if trial_root.is_dir():
        with os.scandir(trial_root) as roots_iterator:
            for item in roots_iterator:
                check_cancel()
                if len(artifacts) >= 64 or remaining <= 0:
                    limited = True
                    break
                remaining -= 1
                path = Path(item.path)
                if not item.is_dir(follow_symlinks=False):
                    continue
                pending = [path]
                size = 0
                complete = True
                reason = "引用尚未核對；保留"
                while pending and remaining > 0:
                    check_cancel()
                    current = pending.pop()
                    try:
                        metadata = current.lstat()
                        if current.is_symlink() or getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                            complete, reason = False, "含連結；未跟隨，保留"
                            continue
                        with os.scandir(current) as children:
                            for child in children:
                                check_cancel()
                                if remaining <= 0:
                                    complete, limited, reason = False, True, "達4096項盤點上限；非完整大小，保留"
                                    break
                                remaining -= 1
                                child_info = child.stat(follow_symlinks=False)
                                if child.is_symlink() or getattr(child_info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                                    complete, reason = False, "含連結；未跟隨，保留"
                                elif child.is_dir(follow_symlinks=False):
                                    pending.append(Path(child.path))
                                elif child.is_file(follow_symlinks=False):
                                    size += child_info.st_size
                    except OSError:
                        complete, reason = False, "部分項目不可讀；保留"
                if pending:
                    complete, limited, reason = False, True, "達4096項盤點上限；非完整大小，保留"
                artifacts.append(StorageArtifact(path.name, size, complete, reason))
    return StorageOverview(tuple(locations), tuple(artifacts), limited)
