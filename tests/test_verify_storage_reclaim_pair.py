"""回收證據必須拒絕缺件、變動、硬連結及鎖定；只使用新隔離fixture。"""
import os
from pathlib import Path
import subprocess

import pytest

from scripts.verify_storage_reclaim_pair import verify_pair, exclusive_probe, resource_users


def pair(tmp_path: Path) -> tuple[Path, Path]:
    a, b = tmp_path / "candidate", tmp_path / "retained"
    for root in (a, b):
        (root / "empty").mkdir(parents=True)
        (root / "runtime.bin").write_bytes(b"runtime" * 1000)
    return a, b


@pytest.mark.skipif(os.name != "nt", reason="需要Windows exclusive metadata handle")
def test_equal_pair_proves_restore_bytes_but_never_authorizes_deletion(tmp_path: Path) -> None:
    a, b = pair(tmp_path)
    result = verify_pair(a, b)
    assert result["equivalent_stable_trees"]
    assert result["verified_file_count"] == 1
    assert result["estimated_candidate_allocation_bytes"] > 0
    assert result["reference_audit_required"] and result["owner_approval_required"]
    assert not result["deletion_performed"]


def test_extra_file_and_empty_directory_are_not_ignored(tmp_path: Path) -> None:
    a, b = pair(tmp_path)
    (a / "unique-evidence.json").write_bytes(b"{}")
    result = verify_pair(a, b)
    assert not result["equivalent_stable_trees"]
    (a / "unique-evidence.json").unlink()
    (a / "unique-empty-directory").mkdir()
    assert not verify_pair(a, b)["equivalent_stable_trees"]


def test_same_size_altered_bytes_fail(tmp_path: Path) -> None:
    a, b = pair(tmp_path)
    (b / "runtime.bin").write_bytes(b"changed" * 1000)
    result = verify_pair(a, b)
    assert not result["equivalent_stable_trees"]
    assert any("hash_differs" in error for error in result["errors"])


def test_hardlink_is_not_reclaimable_duplicate(tmp_path: Path) -> None:
    a, b = pair(tmp_path)
    (b / "runtime.bin").unlink()
    os.link(a / "runtime.bin", b / "runtime.bin")
    result = verify_pair(a, b)
    assert not result["equivalent_stable_trees"]
    assert result["estimated_candidate_allocation_bytes"] is None


def test_overlap_and_hash_budget_fail_closed(tmp_path: Path) -> None:
    a, b = pair(tmp_path)
    assert not verify_pair(a, a)["equivalent_stable_trees"]
    result = verify_pair(a, b, max_hash_bytes=8)
    assert not result["equivalent_stable_trees"]
    assert result["estimated_candidate_allocation_bytes"] is None
    assert result["bytes_hashed"] <= 8
    assert not verify_pair(a, b, max_depth=0)["equivalent_stable_trees"]


@pytest.mark.skipif(os.name != "nt", reason="Windows junction")
def test_junction_ancestor_is_rejected(tmp_path: Path) -> None:
    a, b = pair(tmp_path)
    alias = tmp_path / "alias"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(a)],
                   capture_output=True, check=True)
    try:
        assert not verify_pair(alias, b)["equivalent_stable_trees"]
    finally:
        alias.rmdir()


@pytest.mark.skipif(os.name != "nt", reason="Windows Alternate Data Stream")
def test_unique_alternate_stream_blocks_reclaim(tmp_path: Path) -> None:
    a, b = pair(tmp_path)
    with open(str(a / "runtime.bin") + ":unique", "wb") as stream:
        stream.write(b"unique-evidence")
    result = verify_pair(a, b)
    assert not result["equivalent_stable_trees"]
    assert any("alternate_streams" in error for error in result["errors"])


@pytest.mark.skipif(os.name != "nt", reason="NTFS directory Alternate Data Stream")
def test_unique_directory_stream_blocks_reclaim(tmp_path: Path) -> None:
    a, b = pair(tmp_path)
    with open(str(a / "empty") + ":unique", "wb") as stream:
        stream.write(b"unique-directory-evidence")
    result = verify_pair(a, b)
    assert not result["equivalent_stable_trees"]
    assert any("directory_streams" in error for error in result["errors"])


@pytest.mark.skipif(os.name != "nt", reason="Windows share-mode probe")
def test_open_reader_is_not_misreported_as_no_handles(tmp_path: Path) -> None:
    a, _ = pair(tmp_path)
    with (a / "runtime.bin").open("rb"):
        assert exclusive_probe(a / "runtime.bin") is not None


@pytest.mark.skipif(os.name != "nt", reason="Windows Restart Manager")
def test_restart_manager_sees_the_owned_open_resource(tmp_path: Path) -> None:
    a, _ = pair(tmp_path)
    with (a / "runtime.bin").open("rb"):
        result = resource_users([a / "runtime.bin"])
        assert result["complete"] and result["session_closed"]
        assert os.getpid() in {user["pid"] for user in result["users"]}
