"""只認已設定 repo/output 掛載點的同一實體路徑，不建立跨磁碟來源別名。"""

from __future__ import annotations

import os
from pathlib import Path
import stat
from collections.abc import Mapping


def same_output_scope(existing: object, expected: object, *, repository_root: Path, field: str = "") -> bool:
    """只對具名路徑欄位允許同一 output 掛載點別名。"""
    if existing == expected:
        return True
    if isinstance(existing, Mapping) and isinstance(expected, Mapping):
        return set(existing) == set(expected) and all(
            same_output_scope(existing[key], expected[key], repository_root=repository_root, field=str(key))
            for key in expected
        )
    path_fields = {
        "repository_output_root", "operation_root", "candidate_root", "receipt_root",
        "event_capture_root", "recommendation_root", "state_db", "seed_manifest",
        "baseline", "market_db", "path", "source_path", "data_root",
    }
    return (
        field in path_fields and isinstance(expected, str)
        and same_repository_output_path(existing, Path(expected), repository_root=repository_root)
    )


def same_repository_output_path(
    recorded: object, actual: Path, *, repository_root: Path,
) -> bool:
    """允許既有 output junction 拼法；掛載點以下的新連結一律拒絕。"""
    if not isinstance(recorded, (str, Path)) or not str(recorded).strip():
        return False
    declared = Path(recorded).expanduser()
    target = Path(actual).expanduser()
    if not declared.is_absolute() or not target.is_absolute():
        return False
    declared = Path(os.path.abspath(declared))
    target = Path(os.path.abspath(target))
    if declared == target:
        return True
    try:
        mount = Path(os.path.abspath(repository_root / "output"))
        canonical_mount = mount.resolve(strict=True)

        def inspect(path: Path) -> tuple[int, int]:
            anchors = (mount, canonical_mount)
            selected = next((anchor for anchor in anchors if path.is_relative_to(anchor)), None)
            if selected is None:
                raise ValueError("path_outside_configured_output_mount")
            current = selected
            for part in path.relative_to(selected).parts:
                current = current / part
                info = current.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise ValueError("nested_output_link")
            info = path.stat()
            return info.st_dev, info.st_ino

        declared_before, target_before = inspect(declared), inspect(target)
        if declared.resolve(strict=True) != target.resolve(strict=True):
            return False
        if not declared.resolve(strict=True).is_relative_to(canonical_mount):
            return False
        return (
            declared_before == target_before
            and inspect(declared) == declared_before
            and inspect(target) == target_before
        )
    except (OSError, ValueError, RuntimeError):
        return False
