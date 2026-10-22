"""盤點的邊界與檔案身分防線；測試只建立隔離小檔。"""
import os
from pathlib import Path
import subprocess

import pytest

from scripts.audit_storage_lifecycle import inventory, native_path


def test_hardlinks_and_overlapping_roots_are_not_double_counted(tmp_path: Path) -> None:
    child = tmp_path / "child"
    child.mkdir()
    original = child / "source.bin"
    original.write_bytes(b"x" * 4096)
    os.link(original, child / "second.bin")
    result = inventory([tmp_path, child])
    assert result["totals"]["logical_bytes"] == 16384
    assert result["totals"]["unique_logical_bytes"] == 4096
    assert result["totals"]["duplicate_identity_paths"] == 3
    assert result["safety"]["verified_reclaimable_bytes"] == 0


def test_depth_and_file_budget_report_incomplete_lower_bounds(tmp_path: Path) -> None:
    (tmp_path / "root.bin").write_bytes(b"a")
    child = tmp_path / "child"
    child.mkdir()
    (child / "nested.bin").write_bytes(b"bb")
    result = inventory([tmp_path], max_depth=0)
    assert result["totals"]["unique_logical_bytes"] == 1
    assert not result["complete"]
    assert any(item["reason"] == "depth_budget" for item in result["omissions"])
    result = inventory([tmp_path], max_files=1)
    assert result["totals"]["files"] == 1
    assert not result["complete"]


@pytest.mark.skipif(os.name != "nt", reason="Windows junction 防線")
def test_junction_is_never_followed_even_as_explicit_root(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (target / "protected.bin").write_bytes(b"secret")
    junction = source / "alias"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)],
                   check=True, capture_output=True)
    try:
        result = inventory([source, junction, junction / "nested"])
        assert not result["totals"]
        assert len(result["reparse_points"]) == 3
        assert not result["complete"]
        assert (target / "protected.bin").read_bytes() == b"secret"
    finally:
        junction.rmdir()


def test_missing_roots_and_invalid_budgets_fail_closed(tmp_path: Path) -> None:
    result = inventory([tmp_path / "missing"])
    assert result["errors"] and not result["complete"]
    with pytest.raises(ValueError):
        inventory([tmp_path], max_files=0)


def test_empty_directories_consume_entry_budget(tmp_path: Path) -> None:
    for name in ("one", "two", "three"):
        (tmp_path / name).mkdir()
    result = inventory([tmp_path], max_entries=1)
    assert result["entries_observed"] == 1
    assert result["omissions"] and not result["complete"]


def test_allocation_failure_is_not_a_complete_zero_estimate(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "item.bin").write_bytes(b"evidence")
    monkeypatch.setattr("scripts.audit_storage_lifecycle.allocated_bytes", lambda *args: None)
    result = inventory([tmp_path])
    assert result["totals"]["unknown_allocation_files"] == 1
    assert not result["complete_allocation"] and not result["complete"]
    assert result["safety"]["verified_reclaimable_bytes"] == 0


@pytest.mark.skipif(os.name != "nt", reason="Windows NTFS 配置查詢")
def test_non_aligned_file_reports_cluster_allocation(tmp_path: Path) -> None:
    file = tmp_path / "not-aligned.bin"
    file.write_bytes(b"x" * 65537)
    if file.stat().st_file_attributes & (0x800 | 0x200):
        pytest.skip("此測試限定未壓縮且非 sparse 的本機 NTFS fixture")
    result = inventory([tmp_path])
    assert result["complete_allocation"]
    assert result["totals"]["allocated_bytes"] > 65537


@pytest.mark.skipif(os.name != "nt", reason="Windows extended-length 路徑")
def test_long_paths_are_observed_without_claiming_missing_files(tmp_path: Path) -> None:
    directories = []
    parent = tmp_path
    try:
        for _ in range(4):
            parent = parent / ("long" * 20)
            os.mkdir(native_path(parent))
            directories.append(parent)
        item = parent / "evidence.bin"
        with open(native_path(item), "wb") as stream:
            stream.write(b"evidence")
        result = inventory([tmp_path])
        assert not result["errors"]
        assert result["totals"]["unique_logical_bytes"] == 8
    finally:
        if directories:
            item = directories[-1] / "evidence.bin"
            if os.path.exists(native_path(item)):
                os.unlink(native_path(item))
        for directory in reversed(directories):
            os.rmdir(native_path(directory))
