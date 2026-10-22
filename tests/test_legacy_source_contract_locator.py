from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from data_module import legacy_source_contract_locator as locator


def _locator_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    create_target: bool = True,
) -> tuple[Path, Path, bytes, str]:
    legacy_path = tmp_path / "d" / "source_contract" / "contract.json"
    current_path = tmp_path / "f" / "source_contract" / "contract.json"
    content = b'{"schema_version":"source-contract-test.v1","value":"pinned"}\n'
    pinned_hash = "sha256:" + hashlib.sha256(content).hexdigest()
    monkeypatch.setattr(locator, "LEGACY_SOURCE_CONTRACT_PATH", legacy_path)
    monkeypatch.setattr(locator, "CURRENT_SOURCE_CONTRACT_PATH", current_path)
    monkeypatch.setattr(locator, "PINNED_SOURCE_CONTRACT_SHA256", pinned_hash)
    if create_target:
        current_path.parent.mkdir(parents=True, exist_ok=True)
        current_path.write_bytes(content)
    return legacy_path, current_path, content, pinned_hash


def test_locates_only_exact_pinned_legacy_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    legacy_path, current_path, content, pinned_hash = _locator_fixture(tmp_path, monkeypatch)

    located = locator.locate_legacy_source_contract(
        legacy_path,
        contract_file_sha256=pinned_hash,
    )

    assert located == current_path
    assert located.read_bytes() == content
    assert not legacy_path.exists()


@pytest.mark.parametrize("failure", ("wrong_hash", "wrong_path", "missing_target", "tampered_target"))
def test_rejects_unpinned_or_incomplete_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    legacy_path, current_path, _, pinned_hash = _locator_fixture(
        tmp_path,
        monkeypatch,
        create_target=failure != "missing_target",
    )
    requested_path = legacy_path
    requested_hash = pinned_hash
    if failure == "wrong_hash":
        requested_hash = "sha256:" + "0" * 64
    elif failure == "wrong_path":
        requested_path = legacy_path.parent / "other.json"
    elif failure == "tampered_target":
        current_path.write_bytes(current_path.read_bytes() + b"changed")

    assert (
        locator.locate_legacy_source_contract(
            requested_path,
            contract_file_sha256=requested_hash,
        )
        is None
    )


def test_existing_legacy_contract_is_authoritative(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_path, _, content, pinned_hash = _locator_fixture(tmp_path, monkeypatch)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_bytes(content)

    assert (
        locator.locate_legacy_source_contract(
            legacy_path,
            contract_file_sha256=pinned_hash,
        )
        is None
    )


def test_permission_error_on_legacy_path_does_not_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_path, _, _, pinned_hash = _locator_fixture(tmp_path, monkeypatch)
    real_lstat = locator._lstat

    def deny_legacy(path: Path) -> os.stat_result:
        if path == legacy_path:
            raise PermissionError("access denied")
        return real_lstat(path)

    monkeypatch.setattr(locator, "_lstat", deny_legacy)

    assert (
        locator.locate_legacy_source_contract(
            legacy_path,
            contract_file_sha256=pinned_hash,
        )
        is None
    )


def test_rejects_reparse_ancestor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_path, current_path, content, pinned_hash = _locator_fixture(tmp_path, monkeypatch)
    original_parent = current_path.parent
    outside_parent = tmp_path / "outside"
    outside_parent.mkdir()
    current_path.unlink()
    original_parent.rmdir()
    try:
        os.symlink(outside_parent, original_parent, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink/reparse test unavailable: {type(exc).__name__}")
    (outside_parent / current_path.name).write_bytes(content)
    assert (
        locator.locate_legacy_source_contract(
            legacy_path,
            contract_file_sha256=pinned_hash,
        )
        is None
    )


def test_rejects_hardlinked_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    legacy_path, current_path, content, pinned_hash = _locator_fixture(tmp_path, monkeypatch)
    hardlink_path = current_path.with_name("hardlink.json")
    try:
        os.link(current_path, hardlink_path)
    except OSError as exc:
        pytest.skip(f"hardlink test unavailable: {type(exc).__name__}")
    assert (
        locator.locate_legacy_source_contract(
            legacy_path,
            contract_file_sha256=pinned_hash,
        )
        is None
    )


def _dependency_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    create_target: bool = True,
) -> tuple[Path, Path, bytes, str]:
    origin = tmp_path / "d" / "receipt.json"
    target = tmp_path / "f" / "receipt.json"
    content = b'{"schema_version":"dependency-test.v1"}\n'
    pinned_hash = "sha256:" + hashlib.sha256(content).hexdigest()
    entries = [
        {
            "origin_path": str(origin),
            "current_path": str(target),
            "sha256": pinned_hash,
            "size_bytes": len(content),
        }
    ]
    for index in range(1, 16):
        entries.append(
            {
                "origin_path": str(tmp_path / "d" / f"unused-{index}.json"),
                "current_path": str(tmp_path / "f" / f"unused-{index}.json"),
                "sha256": "sha256:" + f"{index:064x}",
                "size_bytes": 1,
            }
        )
    profile = tmp_path / "profile.json"
    profile_bytes = json.dumps(
        {"schema_version": "legacy-source-contract-locators.v1", "entries": entries},
        separators=(",", ":"),
    ).encode("utf-8")
    profile.write_bytes(profile_bytes)
    monkeypatch.setattr(locator, "LEGACY_SOURCE_CONTRACT_LOCATOR_PROFILE_PATH", profile)
    monkeypatch.setattr(
        locator,
        "LEGACY_SOURCE_CONTRACT_LOCATOR_PROFILE_SHA256",
        "sha256:" + hashlib.sha256(profile_bytes).hexdigest(),
    )
    if create_target:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return origin, target, content, pinned_hash


def test_locates_only_exact_profile_dependency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    origin, target, content, pinned_hash = _dependency_fixture(tmp_path, monkeypatch)

    located = locator.locate_legacy_source_contract_dependency(
        origin,
        expected_sha256=pinned_hash,
    )

    assert located == target
    assert located.read_bytes() == content


@pytest.mark.parametrize("failure", ("wrong_pin", "outside_profile", "missing_target", "tampered"))
def test_rejects_dependency_without_exact_verified_counterpart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    origin, target, _, pinned_hash = _dependency_fixture(
        tmp_path,
        monkeypatch,
        create_target=failure != "missing_target",
    )
    requested_origin = origin
    requested_hash = pinned_hash
    if failure == "wrong_pin":
        requested_hash = "sha256:" + "0" * 64
    elif failure == "outside_profile":
        requested_origin = origin.parent / "other.json"
    elif failure == "tampered":
        target.write_bytes(target.read_bytes() + b"changed")

    assert (
        locator.locate_legacy_source_contract_dependency(
            requested_origin,
            expected_sha256=requested_hash,
        )
        is None
    )


def test_existing_dependency_origin_is_authoritative(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin, _, _, pinned_hash = _dependency_fixture(tmp_path, monkeypatch)
    origin.parent.mkdir(parents=True, exist_ok=True)
    origin.write_bytes(b"legacy authoritative")

    assert (
        locator.locate_legacy_source_contract_dependency(
            origin,
            expected_sha256=pinned_hash,
        )
        is None
    )


def test_permission_error_on_dependency_origin_does_not_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin, _, _, pinned_hash = _dependency_fixture(tmp_path, monkeypatch)
    real_lstat = locator._lstat

    def deny_origin(path: Path) -> os.stat_result:
        if path == origin:
            raise PermissionError("access denied")
        return real_lstat(path)

    monkeypatch.setattr(locator, "_lstat", deny_origin)
    assert (
        locator.locate_legacy_source_contract_dependency(
            origin,
            expected_sha256=pinned_hash,
        )
        is None
    )
