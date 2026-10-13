"""檔案 I/O 的中立路徑渲染；公開路徑與守衛仍由 caller 持有。"""

from __future__ import annotations

from collections.abc import Iterator
import os
from pathlib import Path


def _reject_windows_alias(value: Path) -> None:
    if os.name == "nt" and str(value).startswith(("\\\\?\\", "\\\\.\\")):
        raise ValueError(f"ambiguous_windows_path: {value}")


def to_internal_io_path(path: str | Path, *, force_extended: bool = False) -> str:
    """純詞法渲染；不 resolve、不檢查檔案狀態，也不授 no-follow。"""
    value = Path(path)
    if not value.is_absolute() or ".." in value.parts:
        raise ValueError(f"absolute_path_required: {value}")
    _reject_windows_alias(value)
    if os.name == "nt":
        for part in value.parts[1:]:
            if ":" in part or part.endswith((" ", ".")) or Path(part).is_reserved():
                raise ValueError(f"ambiguous_windows_path: {value}")
    raw = str(value)
    if os.name != "nt" or (not force_extended and len(raw.encode("utf-16-le")) // 2 < 248):
        return raw
    if raw.startswith("\\\\"):
        return "\\\\?\\UNC\\" + raw.lstrip("\\")
    return "\\\\?\\" + raw


def canonical_path_from_os_result(path: str | Path) -> Path:
    """只供本模組發起之 OS 回值使用；不作 caller alias 的入口。"""
    raw = str(path)
    if os.name == "nt":
        folded = raw.casefold()
        if folded.startswith("\\\\?\\unc\\"):
            raw = "\\\\" + raw[8:]
        elif folded.startswith("\\\\?\\"):
            raw = raw[4:]
    value = Path(raw)
    # 重用純詞法檢查，不保存其內部渲染結果作為 identity。
    to_internal_io_path(value)
    return value


def _transport_path(value: Path) -> Path | None:
    """只選可渲染的長路徑；其餘保留原 OS 接口，不新增輸入拒絕。"""
    if os.name != "nt" or ".." in value.parts:
        return None
    absolute = value.absolute()
    raw = str(absolute)
    if raw.startswith(("\\\\?\\", "\\\\.\\")):
        return None
    for part in absolute.parts[1:]:
        if ":" in part or part.endswith((" ", ".")) or Path(part).is_reserved():
            return None
    # 原 OS 可處理的 surrogate 字面值不因純渲染的編碼而提前報錯。
    if any(0xD800 <= ord(char) <= 0xDFFF for char in raw):
        return None
    if len(raw.encode("utf-16-le")) // 2 < 248:
        return None
    return Path(to_internal_io_path(absolute))


def io_path(path: str | Path) -> Path:
    """只在 OS 接點選 transport；短、relative/dotdot/alias 回原 Path。"""
    value = Path(path)
    transport = _transport_path(value)
    return value if transport is None else transport


def resolve_canonical_path(path: str | Path, *, strict: bool = False) -> Path:
    """保留原 relative／dotdot resolve 語義，OS 回值維持 canonical。"""
    value = Path(path)
    transport = _transport_path(value)
    if transport is None:
        # 原 relative/dotdot/ambiguous、strict 與 symlink-loop 行為原樣執行。
        return value.resolve(strict=strict)
    return canonical_path_from_os_result(transport.resolve(strict=strict))


def canonical_scandir_child(parent: Path, name: str, os_path: str | Path) -> Path:
    """由 canonical parent／basename 重建，再精確核對自有 OS 回值。"""
    if not name or name in {".", ".."} or Path(name).name != name:
        raise ValueError("candidate package contains an unrecognized entry")
    expected = parent / name
    returned = Path(os_path)
    if returned.is_absolute():
        actual = canonical_path_from_os_result(returned)
        expected_os = expected.absolute()
        if actual != expected_os or actual.parent != expected_os.parent:
            raise ValueError("candidate package contains an unrecognized entry")
    elif returned != expected or returned.parent != parent:
        raise ValueError("candidate package contains an unrecognized entry")
    return expected


def iterdir_canonical(path: Path) -> Iterator[Path]:
    """保持原列舉時點與排序責任，OS child prefix 不進公開 Path。"""
    for child in io_path(path).iterdir():
        yield canonical_scandir_child(path, child.name, child)
