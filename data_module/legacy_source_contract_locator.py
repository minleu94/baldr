"""只定位一份已由外部 SHA 固定的舊來源契約，不改寫原件。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat


LEGACY_SOURCE_CONTRACT_PATH = Path(
    r"D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\source_contract\2026-09-14\e799ddb93626edef\contract.json"
)
CURRENT_SOURCE_CONTRACT_PATH = Path(
    r"F:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\source_contract\2026-09-14\e799ddb93626edef\contract.json"
)
PINNED_SOURCE_CONTRACT_SHA256 = (
    "sha256:22cba7aa0cb57cb7775b7423515059c853bd8b893984ee7fbe6bdd79b7366183"
)
MAX_SOURCE_CONTRACT_BYTES = 2 * 1024 * 1024
LEGACY_SOURCE_CONTRACT_LOCATOR_PROFILE_PATH = Path(__file__).with_name(
    "legacy_source_contract_locators_20261020.json"
)
LEGACY_SOURCE_CONTRACT_LOCATOR_PROFILE_SHA256 = (
    "sha256:d0122a70ab2a48e6bd5f935b4cf70bcc02346ceb544af8cba846a51b96fdabd7"
)
MAX_LOCATOR_PROFILE_BYTES = 32 * 1024
MAX_LOCATED_DEPENDENCY_BYTES = 8 * 1024 * 1024
_REPARSE_ATTRIBUTE = 0x400


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """拒絕定位清單中的重複 JSON 欄位。"""

    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("定位清單含重複 JSON 欄位")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> object:
    """拒絕 JSON 規格外的 NaN 與 Infinity 常數。"""

    raise ValueError("定位清單含非法 JSON 常數")


def _read_verified_locator_profile() -> list[dict[str, object]] | None:
    """讀取外部 SHA 固定且內容受限的逐檔定位清單。"""

    path = LEGACY_SOURCE_CONTRACT_LOCATOR_PROFILE_PATH
    if not _plain_target_ancestors(path):
        return None
    try:
        before = _lstat(path)
    except OSError:
        return None
    if (
        not stat.S_ISREG(before.st_mode)
        or _is_reparse(path, before)
        or before.st_nlink != 1
        or before.st_size < 0
        or before.st_size > MAX_LOCATOR_PROFILE_BYTES
    ):
        return None
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        opened_before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_before.st_mode)
            or opened_before.st_nlink != 1
            or _is_reparse(path, opened_before)
            or _identity(opened_before) != _identity(before)
        ):
            return None
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read(MAX_LOCATOR_PROFILE_BYTES + 1)
        opened_after = os.fstat(descriptor)
        try:
            after = _lstat(path)
        except OSError:
            return None
        if (
            len(content) > MAX_LOCATOR_PROFILE_BYTES
            or _identity(opened_after) != _identity(opened_before)
            or _identity(after) != _identity(before)
            or not stat.S_ISREG(after.st_mode)
            or _is_reparse(path, after)
            or after.st_nlink != 1
            or not _plain_target_ancestors(path)
            or "sha256:" + hashlib.sha256(content).hexdigest()
            != LEGACY_SOURCE_CONTRACT_LOCATOR_PROFILE_SHA256
        ):
            return None
    finally:
        os.close(descriptor)
    try:
        payload = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "entries"}:
        return None
    if payload.get("schema_version") != "legacy-source-contract-locators.v1":
        return None
    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) != 16:
        return None
    origins: set[str] = set()
    currents: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "origin_path", "current_path", "sha256", "size_bytes"
        }:
            return None
        origin = entry.get("origin_path")
        current = entry.get("current_path")
        digest = entry.get("sha256")
        size = entry.get("size_bytes")
        if (
            not isinstance(origin, str)
            or not isinstance(current, str)
            or not isinstance(digest, str)
            or len(digest) != 71
            or not digest.startswith("sha256:")
            or any(character not in "0123456789abcdef" for character in digest[7:])
            or type(size) is not int
            or size < 0
            or size > MAX_LOCATED_DEPENDENCY_BYTES
            or origin in origins
            or current in currents
        ):
            return None
        origins.add(origin)
        currents.add(current)
    return entries


def locate_legacy_source_contract_dependency(
    dependency_path: str | Path,
    *,
    expected_sha256: str,
) -> Path | None:
    """只定位清單逐檔固定的缺失依賴，且不改變原始契約內容。"""

    try:
        origin_text = os.fspath(dependency_path)
    except TypeError:
        return None
    if not isinstance(origin_text, str):
        return None
    entries = _read_verified_locator_profile()
    if entries is None:
        return None
    entry = next(
        (
            candidate
            for candidate in entries
            if candidate.get("origin_path") == origin_text
            and candidate.get("sha256") == expected_sha256
        ),
        None,
    )
    if entry is None:
        return None
    origin_path = Path(origin_text)
    try:
        _lstat(origin_path)
    except FileNotFoundError:
        pass
    except OSError:
        return None
    else:
        return None
    target = Path(str(entry["current_path"]))
    size = entry["size_bytes"]
    if not isinstance(size, int) or size > MAX_LOCATED_DEPENDENCY_BYTES:
        return None
    if not _read_pinned_profile_target(target, expected_sha256, size):
        return None
    return target


def _read_pinned_profile_target(path: Path, expected_sha256: str, expected_size: int) -> bool:
    """驗證清單目標為普通單連結檔，並核對穩定讀取前後的身分與 SHA。"""

    if not _plain_target_ancestors(path):
        return False
    try:
        before = _lstat(path)
    except OSError:
        return False
    if (
        not stat.S_ISREG(before.st_mode)
        or _is_reparse(path, before)
        or before.st_nlink != 1
        or before.st_size != expected_size
        or before.st_size < 0
        or before.st_size > MAX_LOCATED_DEPENDENCY_BYTES
    ):
        return False
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return False
    try:
        opened_before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_before.st_mode)
            or opened_before.st_nlink != 1
            or _is_reparse(path, opened_before)
            or _identity(opened_before) != _identity(before)
        ):
            return False
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read(MAX_LOCATED_DEPENDENCY_BYTES + 1)
        opened_after = os.fstat(descriptor)
        try:
            after = _lstat(path)
        except OSError:
            return False
        if (
            len(content) != expected_size
            or _identity(opened_after) != _identity(opened_before)
            or _identity(after) != _identity(before)
            or not stat.S_ISREG(after.st_mode)
            or _is_reparse(path, after)
            or after.st_nlink != 1
            or not _plain_target_ancestors(path)
        ):
            return False
        return "sha256:" + hashlib.sha256(content).hexdigest() == expected_sha256
    finally:
        os.close(descriptor)


def _lstat(path: Path) -> os.stat_result:
    return path.lstat()


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_size),
        int(getattr(metadata, "st_mtime_ns", int(metadata.st_mtime * 1_000_000_000))),
        int(getattr(metadata, "st_ctime_ns", int(metadata.st_ctime * 1_000_000_000))),
        int(metadata.st_nlink),
    )


def _is_reparse(path: Path, metadata: os.stat_result) -> bool:
    return path.is_symlink() or bool(
        getattr(metadata, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE
    )


def _plain_target_ancestors(path: Path) -> bool:
    anchor = Path(path.anchor)
    try:
        metadata = _lstat(anchor)
    except OSError:
        return False
    if not stat.S_ISDIR(metadata.st_mode) or _is_reparse(anchor, metadata):
        return False
    current = anchor
    for component in path.parts[1:-1]:
        if component in ("", ".", ".."):
            return False
        current = current / component
        try:
            metadata = _lstat(current)
        except OSError:
            return False
        if not stat.S_ISDIR(metadata.st_mode) or _is_reparse(current, metadata):
            return False
    return True


def _read_pinned_target(path: Path, expected_sha256: str) -> bool:
    if not _plain_target_ancestors(path):
        return False
    try:
        before = _lstat(path)
    except OSError:
        return False
    if (
        not stat.S_ISREG(before.st_mode)
        or _is_reparse(path, before)
        or before.st_nlink != 1
        or before.st_size < 0
        or before.st_size > MAX_SOURCE_CONTRACT_BYTES
    ):
        return False

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return False
    try:
        opened_before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_before.st_mode)
            or opened_before.st_nlink != 1
            or _identity(opened_before) != _identity(before)
            or _is_reparse(path, opened_before)
        ):
            return False
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read(MAX_SOURCE_CONTRACT_BYTES + 1)
        opened_after = os.fstat(descriptor)
        try:
            after = _lstat(path)
        except OSError:
            return False
        if (
            len(content) > MAX_SOURCE_CONTRACT_BYTES
            or _identity(opened_after) != _identity(opened_before)
            or _identity(after) != _identity(before)
            or not stat.S_ISREG(after.st_mode)
            or _is_reparse(path, after)
            or after.st_nlink != 1
            or not _plain_target_ancestors(path)
        ):
            return False
        actual_sha256 = "sha256:" + hashlib.sha256(content).hexdigest()
        return actual_sha256 == expected_sha256 == PINNED_SOURCE_CONTRACT_SHA256
    finally:
        os.close(descriptor)


def locate_legacy_source_contract(
    contract_path: str | Path,
    *,
    contract_file_sha256: str,
) -> Path | None:
    """僅定位該份缺失的 D 原件；caller 仍須核正文、自身雜湊與來源資格。"""

    raw_path = Path(contract_path).expanduser()
    if raw_path != LEGACY_SOURCE_CONTRACT_PATH:
        return None
    if contract_file_sha256 != PINNED_SOURCE_CONTRACT_SHA256:
        return None
    try:
        _lstat(raw_path)
    except FileNotFoundError:
        pass
    except OSError:
        return None
    else:
        return None
    target = CURRENT_SOURCE_CONTRACT_PATH
    if not _read_pinned_target(target, contract_file_sha256):
        return None
    return target
