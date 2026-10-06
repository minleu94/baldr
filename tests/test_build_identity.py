from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

import app_module.build_identity as build_identity_module
from app_module.build_identity import BuildIdentity, detect_build_identity


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Codex Test",
            "GIT_AUTHOR_EMAIL": "codex-test@example.invalid",
            "GIT_COMMITTER_NAME": "Codex Test",
            "GIT_COMMITTER_EMAIL": "codex-test@example.invalid",
        },
    )
    return result.stdout.strip()


def _git_repository(tmp_path: Path) -> tuple[Path, str]:
    if shutil.which("git") is None:
        pytest.skip("Git is required for checkout identity tests")
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    (repository / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    author_environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Codex Test",
        "GIT_AUTHOR_EMAIL": "codex-test@example.invalid",
        "GIT_COMMITTER_NAME": "Codex Test",
        "GIT_COMMITTER_EMAIL": "codex-test@example.invalid",
    }
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-m", "baseline", "--quiet"],
        check=True,
        capture_output=True,
        text=True,
        env=author_environment,
    )
    return repository, _git(repository, "rev-parse", "HEAD")


def _lock(repository: Path, contents: str = '{"dependencies":[]}\n') -> str:
    lock_path = repository / "packaging" / "windows-dependencies.lock.json"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(contents, encoding="utf-8")
    return hashlib.sha256(lock_path.read_bytes()).hexdigest()


def _write_metadata(
    path: Path,
    *,
    commit: str,
    lock_hash: str,
    channel: str = "release",
    dirty: bool = False,
    version: str | None = None,
    resource_hashes: dict[str, str] | None = None,
) -> None:
    if resource_hashes is None:
        default_resource = path.parent / "ui_qt" / "app_icon.png"
        default_resource.parent.mkdir(parents=True, exist_ok=True)
        default_resource.write_bytes(b"test icon bytes")
        resource_hashes = {
            "ui_qt/app_icon.png": hashlib.sha256(default_resource.read_bytes()).hexdigest()
        }
    payload = {
        "schema": "baldr-application-build.v1",
        "version": version or f"2026.10.06+{commit[:12]}",
        "source_commit": commit,
        "channel": channel,
        "dirty": dirty,
        "dependency_lock_sha256": lock_hash,
        "resource_sha256": resource_hashes,
        "BUILD_INFO": {"receipt": "extra fields are tolerated"},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_git_checkout_reports_actual_head_and_clean_status(tmp_path: Path) -> None:
    repository, _ = _git_repository(tmp_path)
    lock_hash = _lock(repository)
    _git(repository, "add", "packaging/windows-dependencies.lock.json")
    _git(repository, "commit", "-m", "lock dependencies", "--quiet")
    expected_commit = _git(repository, "rev-parse", "HEAD")

    identity = detect_build_identity(repository_root=repository, frozen=False)

    assert identity.source_commit == expected_commit
    assert identity.version.endswith(f"+{expected_commit[:12]}")
    assert re.fullmatch(r"\d{4}\.\d{2}\.\d{2}\+[0-9a-f]{12}", identity.version)
    assert identity.channel == "development"
    assert identity.dirty is False
    assert identity.dependency_lock_sha256 == lock_hash


def test_git_checkout_detects_tracked_and_untracked_changes(tmp_path: Path) -> None:
    repository, _ = _git_repository(tmp_path)
    (repository / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (repository / "new-file.txt").write_text("untracked\n", encoding="utf-8")

    identity = detect_build_identity(repository_root=repository, frozen=False)

    assert identity.channel == "development"
    assert identity.dirty is True


def test_git_checkout_does_not_trust_embedded_release_metadata(tmp_path: Path) -> None:
    repository, expected_commit = _git_repository(tmp_path)
    lock_hash = _lock(repository)
    metadata = repository / "application_build.json"
    _write_metadata(metadata, commit="a" * 40, lock_hash=lock_hash)

    identity = detect_build_identity(repository_root=repository, frozen=False)

    assert identity.source_commit == expected_commit
    assert identity.channel == "development"
    assert identity.dirty is True


def test_frozen_source_accepts_verified_metadata_and_lock_hash(tmp_path: Path) -> None:
    source_root = tmp_path / "fixed-source"
    source_root.mkdir()
    lock_hash = _lock(source_root)
    commit = "1234567890abcdef1234567890abcdef12345678"
    metadata = source_root / "application_build.json"
    _write_metadata(metadata, commit=commit, lock_hash=lock_hash)

    identity = detect_build_identity(
        repository_root=source_root, metadata_path=metadata, frozen=True
    )

    assert identity == BuildIdentity(
        version=f"2026.10.06+{commit[:12]}",
        source_commit=commit,
        channel="release",
        dirty=False,
        dependency_lock_sha256=lock_hash,
    )
    assert "未核實" not in identity.display_text
    assert "發布版" in identity.display_text
    assert "已提交原碼" in identity.display_text
    assert commit not in identity.display_text
    assert identity.to_dict()["display_text"] == identity.display_text
    json.dumps(identity.to_dict())


def test_untracked_source_snapshot_uses_verified_metadata(tmp_path: Path) -> None:
    source_root = tmp_path / "snapshot"
    source_root.mkdir()
    lock_hash = _lock(source_root)
    commit = "abcdef0123456789abcdef0123456789abcdef01"
    _write_metadata(source_root / "application_build.json", commit=commit, lock_hash=lock_hash)

    identity = detect_build_identity(repository_root=source_root, frozen=False)

    assert identity.source_commit == commit
    assert identity.channel == "release"
    assert identity.dirty is False


def test_source_archive_inside_git_checkout_uses_same_metadata_as_frozen(
    tmp_path: Path,
) -> None:
    repository, ancestor_commit = _git_repository(tmp_path)
    source_root = repository / "output" / "packaging" / "build_candidate" / "source"
    source_root.mkdir(parents=True)
    lock_hash = _lock(source_root)
    source_commit = "abcdef0123456789abcdef0123456789abcdef01"
    _write_metadata(
        source_root / "application_build.json",
        commit=source_commit,
        lock_hash=lock_hash,
    )

    python_identity = detect_build_identity(repository_root=source_root, frozen=False)
    frozen_identity = detect_build_identity(repository_root=source_root, frozen=True)

    assert python_identity == frozen_identity
    assert python_identity.source_commit == source_commit
    assert python_identity.source_commit != ancestor_commit
    assert python_identity.channel == "release"


def test_metadata_with_missing_dependency_lock_is_unverified(tmp_path: Path) -> None:
    source_root = tmp_path / "snapshot"
    source_root.mkdir()
    lock_hash = _lock(source_root)
    commit = "abcdef0123456789abcdef0123456789abcdef01"
    metadata = source_root / "application_build.json"
    _write_metadata(metadata, commit=commit, lock_hash=lock_hash)
    (source_root / "packaging" / "windows-dependencies.lock.json").unlink()

    identity = detect_build_identity(
        repository_root=source_root, metadata_path=metadata, frozen=True
    )

    assert identity.source_commit == "unknown"
    assert identity.channel == "unverified"


def test_metadata_missing_a_ui_resource_hash_is_unverified(tmp_path: Path) -> None:
    source_root = tmp_path / "snapshot"
    extra_resource = source_root / "ui_qt" / "assets" / "theme.qss"
    extra_resource.parent.mkdir(parents=True)
    extra_resource.write_text("QWidget {}", encoding="utf-8")
    lock_hash = _lock(source_root)
    commit = "abcdef0123456789abcdef0123456789abcdef01"
    _write_metadata(
        source_root / "application_build.json", commit=commit, lock_hash=lock_hash
    )

    identity = detect_build_identity(repository_root=source_root, frozen=True)

    assert identity.source_commit == "unknown"
    assert identity.channel == "unverified"


def test_frozen_without_meipass_reads_metadata_from_executable_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    commit = "1234567890abcdef1234567890abcdef12345678"
    _write_metadata(
        package_root / "application_build.json",
        commit=commit,
        lock_hash=_lock(package_root),
    )
    monkeypatch.setattr(sys, "executable", str(package_root / "baldr.exe"))
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    identity = detect_build_identity(frozen=True)

    assert identity.source_commit == commit
    assert identity.channel == "release"
    assert identity.dirty is False


@pytest.mark.parametrize(
    "metadata_overrides",
    [
        {"dirty": True},
        {"channel": "release-candidate"},
        {"schema": "old-schema"},
        {"version": "2026.10.06+000000000000"},
        {"dependency_lock_sha256": "not-a-sha256"},
        {"source_commit": "short"},
        {"source_commit": "A" * 40},
        {"dependency_lock_sha256": "A" * 64},
        {"resource_sha256": None},
    ],
)
def test_malformed_or_unverified_metadata_is_not_accepted(
    tmp_path: Path, metadata_overrides: dict[str, object]
) -> None:
    source_root = tmp_path / "snapshot"
    source_root.mkdir()
    lock_hash = _lock(source_root)
    commit = "abcdef0123456789abcdef0123456789abcdef01"
    payload: dict[str, object] = {
        "schema": "baldr-application-build.v1",
        "version": f"2026.10.06+{commit[:12]}",
        "source_commit": commit,
        "channel": "release",
        "dirty": False,
        "dependency_lock_sha256": lock_hash,
        "resource_sha256": {},
    }
    payload.update(metadata_overrides)
    metadata = source_root / "application_build.json"
    metadata.write_text(json.dumps(payload), encoding="utf-8")

    identity = detect_build_identity(
        repository_root=source_root, metadata_path=metadata, frozen=True
    )

    assert identity.source_commit == "unknown"
    assert identity.channel == "unverified"
    assert "未核實" in identity.display_text


def test_metadata_lock_hash_must_match_available_lock_file(tmp_path: Path) -> None:
    source_root = tmp_path / "snapshot"
    source_root.mkdir()
    actual_hash = _lock(source_root)
    commit = "abcdef0123456789abcdef0123456789abcdef01"
    metadata = source_root / "application_build.json"
    _write_metadata(metadata, commit=commit, lock_hash="0" * 64)

    identity = detect_build_identity(
        repository_root=source_root, metadata_path=metadata, frozen=True
    )

    assert actual_hash != identity.dependency_lock_sha256
    assert identity.channel == "unverified"


def test_metadata_resource_hashes_are_verified_against_source_root(tmp_path: Path) -> None:
    source_root = tmp_path / "snapshot"
    resource_path = source_root / "ui_qt" / "app_icon.png"
    resource_path.parent.mkdir(parents=True)
    resource_path.write_bytes(b"icon-bytes")
    lock_hash = _lock(source_root)
    commit = "abcdef0123456789abcdef0123456789abcdef01"
    metadata = source_root / "application_build.json"
    resource_hash = hashlib.sha256(resource_path.read_bytes()).hexdigest()
    _write_metadata(
        metadata,
        commit=commit,
        lock_hash=lock_hash,
        resource_hashes={"ui_qt/app_icon.png": resource_hash},
    )

    identity = detect_build_identity(
        repository_root=source_root, metadata_path=metadata, frozen=True
    )

    assert identity.source_commit == commit
    assert identity.channel == "release"

    resource_path.write_bytes(b"tampered")
    changed = detect_build_identity(
        repository_root=source_root, metadata_path=metadata, frozen=True
    )
    assert changed.source_commit == "unknown"
    assert changed.channel == "unverified"


def test_git_failure_with_git_marker_does_not_fall_back_to_release_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository, _ = _git_repository(tmp_path)
    lock_hash = _lock(repository)
    _write_metadata(
        repository / "application_build.json",
        commit="abcdef0123456789abcdef0123456789abcdef01",
        lock_hash=lock_hash,
    )
    monkeypatch.setattr(build_identity_module.shutil, "which", lambda _name: None)

    identity = detect_build_identity(repository_root=repository, frozen=False)

    assert identity.source_commit == "unknown"
    assert identity.channel == "unverified"
    assert identity.dirty is True


def test_missing_metadata_and_git_reports_unknown_source_commit(tmp_path: Path) -> None:
    source_root = tmp_path / "source-without-git"
    source_root.mkdir()

    identity = detect_build_identity(repository_root=source_root, frozen=False)

    assert identity.source_commit == "unknown"
    assert identity.channel == "unverified"
    assert identity.version == "unknown"
    assert "未核實" in identity.display_text
