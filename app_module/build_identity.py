"""讀取 Baldr Python 與 frozen 套件共用的建置身分。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any


_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_LOCK_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_VERSION_RE = re.compile(r"^(\d{4}\.\d{2}\.\d{2})\+([0-9a-f]{12})$")
_BUILD_SCHEMA = "baldr-application-build.v1"
_MAX_METADATA_BYTES = 64 * 1024


@dataclass(frozen=True)
class BuildIdentity:
    """可顯示及序列化的建置版本身分。"""

    version: str
    source_commit: str
    channel: str
    dirty: bool
    dependency_lock_sha256: str | None

    @property
    def display_text(self) -> str:
        if self.channel == "unverified" or self.source_commit == "unknown":
            return "未核實版本｜來源或建置 metadata 未通過檢查"
        channel_text = "開發版" if self.channel == "development" else "發布版"
        state_text = "含未提交變更" if self.dirty else "已提交原碼"
        return f"{self.version}｜{channel_text}｜{state_text}"

    def to_dict(self) -> dict[str, Any]:
        """回傳可供 JSON 序列化的建置身分。"""

        return {
            "version": self.version,
            "source_commit": self.source_commit,
            "channel": self.channel,
            "dirty": self.dirty,
            "dependency_lock_sha256": self.dependency_lock_sha256,
            "display_text": self.display_text,
        }


def detect_build_identity(
    repository_root: Path | None = None,
    metadata_path: Path | None = None,
    frozen: bool | None = None,
) -> BuildIdentity:
    """從目前 Git checkout 或已驗證的 application_build.json 讀取身分。"""

    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if not isinstance(is_frozen, bool):
        return _unverified_identity()

    if is_frozen and getattr(sys, "_MEIPASS", None):
        default_root = Path(getattr(sys, "_MEIPASS"))
    elif is_frozen and getattr(sys, "executable", None):
        default_root = Path(sys.executable).parent
    else:
        default_root = Path(__file__).resolve().parents[1]
    root = _canonical_path(Path(repository_root) if repository_root is not None else default_root)
    selected_metadata = _metadata_location(metadata_path, root)

    if not is_frozen:
        git_identity = _read_git_identity(root)
        if git_identity is not None:
            return git_identity
        if _has_git_marker(root):
            # Git 存在但命令失敗時，不能讓舊 metadata 把錯誤狀態說成 clean release。
            return _unverified_identity()

    metadata_root = root
    if repository_root is None and metadata_path is not None:
        metadata_root = selected_metadata.parent
    return _read_verified_metadata(selected_metadata, metadata_root)


def _read_git_identity(root: Path) -> BuildIdentity | None:
    if not root.is_dir() or shutil.which("git") is None:
        return None

    git_environment = os.environ.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        git_environment.pop(key, None)
    git_environment["GIT_OPTIONAL_LOCKS"] = "0"

    try:
        top_level_result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            env=git_environment,
        )
        if top_level_result.returncode != 0:
            return None
        top_level = _canonical_path(Path(top_level_result.stdout.strip()))
        if top_level != _canonical_path(root):
            # 固定來源 archive 常位於 Git checkout 的子目錄；只認自己的 checkout。
            return None

        commit_result = subprocess.run(
            ["git", "-C", str(top_level), "rev-parse", "--verify", "HEAD^{commit}"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            env=git_environment,
        )
        source_commit = commit_result.stdout.strip().lower()
        if commit_result.returncode != 0 or not _COMMIT_RE.fullmatch(source_commit):
            return None

        status_result = subprocess.run(
            [
                "git",
                "-C",
                str(top_level),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignore-submodules=none",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            env=git_environment,
        )
        if status_result.returncode != 0:
            return None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None

    return BuildIdentity(
        version=f"{date.today():%Y.%m.%d}+{source_commit[:12]}",
        source_commit=source_commit,
        channel="development",
        dirty=bool(status_result.stdout.strip()),
        dependency_lock_sha256=_lock_sha256(top_level),
    )


def _read_verified_metadata(metadata_path: Path, source_root: Path) -> BuildIdentity:
    try:
        if not metadata_path.is_file() or metadata_path.stat().st_size > _MAX_METADATA_BYTES:
            return _unverified_identity()
        payload = json.loads(
            metadata_path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return _unverified_identity()

    if not isinstance(payload, dict):
        return _unverified_identity()
    version = payload.get("version")
    source_commit = payload.get("source_commit")
    channel = payload.get("channel")
    dirty = payload.get("dirty")
    lock_hash = payload.get("dependency_lock_sha256")
    if (
        payload.get("schema") != _BUILD_SCHEMA
        or not isinstance(version, str)
        or not isinstance(source_commit, str)
        or not isinstance(channel, str)
        or dirty is not False
        or not isinstance(lock_hash, str)
        or not isinstance(payload.get("resource_sha256"), dict)
    ):
        return _unverified_identity()

    normalized_commit = source_commit
    normalized_lock_hash = lock_hash
    version_match = _VERSION_RE.fullmatch(version)
    if (
        not _COMMIT_RE.fullmatch(normalized_commit)
        or not _LOCK_HASH_RE.fullmatch(normalized_lock_hash)
        or channel not in ("development", "release")
        or version_match is None
        or version_match.group(2) != normalized_commit[:12]
    ):
        return _unverified_identity()
    try:
        datetime.strptime(version_match.group(1), "%Y.%m.%d")
    except ValueError:
        return _unverified_identity()

    lock_root = source_root if source_root.is_dir() else metadata_path.parent
    actual_lock_hash = _lock_sha256(lock_root)
    if actual_lock_hash is None or actual_lock_hash != normalized_lock_hash:
        return _unverified_identity()
    if not _verify_resource_manifest(
        source_root=source_root,
        resource_manifest=payload["resource_sha256"],
    ):
        return _unverified_identity()

    return BuildIdentity(
        version=version,
        source_commit=normalized_commit,
        channel=channel,
        dirty=False,
        dependency_lock_sha256=normalized_lock_hash,
    )


def _metadata_location(metadata_path: Path | None, root: Path) -> Path:
    if metadata_path is None:
        return root / "application_build.json"
    candidate = Path(metadata_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    return _canonical_path(candidate)


def _lock_sha256(repository_root: Path) -> str | None:
    lock_path = repository_root / "packaging" / "windows-dependencies.lock.json"
    try:
        if not lock_path.is_file():
            return None
        return hashlib.sha256(lock_path.read_bytes()).hexdigest()
    except OSError:
        return None


def _verify_resource_manifest(
    *, source_root: Path, resource_manifest: dict[str, Any]
) -> bool:
    root = _canonical_path(source_root)
    if not resource_manifest:
        return False
    ui_root = root / "ui_qt"
    expected_resources = {
        path.relative_to(root).as_posix()
        for path in ui_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".png", ".ico", ".qss"}
    }
    if "ui_qt/app_icon.png" not in expected_resources:
        return False
    if not expected_resources.issubset(resource_manifest):
        return False
    for relative_path, expected_hash in resource_manifest.items():
        if (
            not isinstance(relative_path, str)
            or not relative_path.strip()
            or not isinstance(expected_hash, str)
            or not _LOCK_HASH_RE.fullmatch(expected_hash)
        ):
            return False
        candidate = Path(relative_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            return False
        resolved = _canonical_path(root / candidate)
        if not _is_same_or_child(resolved, root) or not resolved.is_file():
            return False
        try:
            actual_hash = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except OSError:
            return False
        if actual_hash != expected_hash.lower():
            return False
    return True


def _is_same_or_child(candidate: Path, parent: Path) -> bool:
    candidate_key = os.path.normcase(str(_canonical_path(candidate))).rstrip("\\/").casefold()
    parent_key = os.path.normcase(str(_canonical_path(parent))).rstrip("\\/").casefold()
    return candidate_key == parent_key or candidate_key.startswith(
        parent_key + os.sep.casefold()
    )


def _has_git_marker(root: Path) -> bool:
    try:
        (root / ".git").lstat()
    except FileNotFoundError:
        return False
    except OSError:
        # 無法確認自己的 Git metadata 時，採未核實路徑，不能信任舊 release metadata。
        return True
    return True


def _canonical_path(path: Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve(strict=False)


def _unverified_identity() -> BuildIdentity:
    return BuildIdentity(
        version="unknown",
        source_commit="unknown",
        channel="unverified",
        dirty=True,
        dependency_lock_sha256=None,
    )


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("metadata 不可包含重複鍵")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"metadata 不支援 JSON 常數：{value}")
