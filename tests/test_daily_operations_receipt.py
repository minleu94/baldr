"""每日營運終態收據寫入器的 create-only 測試。"""

from pathlib import Path
import hashlib
import os
import subprocess

import pytest

from scripts.scheduled import daily_operations_receipt as receipt_writer


def test_terminal_receipt_is_create_only_and_hashes_written_bytes(tmp_path: Path) -> None:
    """同一路徑不覆寫，回傳 SHA 對應落盤的完整原始位元組。"""
    path = tmp_path / "receipts" / "run.json"
    reference = receipt_writer.write_terminal_receipt(path, {"run_id": "run-1", "status": "passed"})
    raw = path.read_bytes()
    assert reference["path"] == str(path)
    assert reference["sha256"] == "sha256:" + hashlib.sha256(raw).hexdigest()
    existing_bytes = raw
    with pytest.raises(FileExistsError):
        receipt_writer.write_terminal_receipt(path, {"run_id": "run-2"})
    assert path.read_bytes() == existing_bytes


def test_failed_create_only_write_removes_partial_receipt(tmp_path: Path, monkeypatch) -> None:
    """寫入途中失敗會清除本次建立的半成品。"""
    path = tmp_path / "receipts" / "run.json"
    original_write = receipt_writer.os.write
    calls = 0

    def fail_after_partial(descriptor: int, value: memoryview) -> int:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise OSError("fixture short write")
        return original_write(descriptor, value[:2])

    monkeypatch.setattr(receipt_writer.os, "write", fail_after_partial)
    with pytest.raises(OSError, match="fixture short write"):
        receipt_writer.write_terminal_receipt(path, {"run_id": "run-1"})
    assert not path.exists()


def test_partial_cleanup_preserves_replaced_path_identity(tmp_path: Path, monkeypatch) -> None:
    """清理時路徑已指向別的檔案，就保留該新檔。"""
    path = tmp_path / "receipts" / "run.json"
    displaced = path.with_name("displaced.json")
    original_write = receipt_writer.os.write
    original_close = receipt_writer.os.close
    calls = 0

    def fail_after_partial(descriptor: int, value: memoryview) -> int:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise OSError("fixture short write")
        return original_write(descriptor, value[:2])

    def replace_after_close(descriptor: int) -> None:
        original_close(descriptor)
        if path.exists():
            path.rename(displaced)
        path.write_bytes(b"replacement")

    monkeypatch.setattr(receipt_writer.os, "write", fail_after_partial)
    monkeypatch.setattr(receipt_writer.os, "close", replace_after_close)
    with pytest.raises(OSError, match="fixture short write"):
        receipt_writer.write_terminal_receipt(path, {"run_id": "run-1"})
    assert path.read_bytes() == b"replacement"


def test_invalid_json_values_are_rejected_before_file_creation(tmp_path: Path) -> None:
    """非有限數值及未定義物件不會被靜默字串化或落盤。"""
    nan_path = tmp_path / "receipts" / "nan.json"
    object_path = tmp_path / "receipts" / "object.json"
    with pytest.raises(ValueError):
        receipt_writer.write_terminal_receipt(nan_path, {"value": float("nan")})
    with pytest.raises(TypeError):
        receipt_writer.write_terminal_receipt(object_path, {"value": object()})
    assert not nan_path.exists()
    assert not object_path.exists()


def test_terminal_receipt_rejects_outside_explicit_root(tmp_path: Path) -> None:
    """明示收據根以外不建立任何檔案。"""
    target = tmp_path / "outside" / "run.json"
    with pytest.raises(ValueError, match="outside_root"):
        receipt_writer.write_terminal_receipt(target, {}, receipt_root=tmp_path / "allowed")
    assert not target.parent.exists()


def test_terminal_receipt_rejects_junction_parent_before_writing(tmp_path: Path) -> None:
    """Windows目錄junction不授予寫入其目標的權限。"""
    if os.name != "nt":
        pytest.skip("requires Windows directory junction")
    root = tmp_path / "allowed"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "receipts"
    result = subprocess.run(
        f'cmd.exe /d /s /c mklink /J "{link}" "{outside}"',
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    with pytest.raises(ValueError, match="contains_link"):
        receipt_writer.write_terminal_receipt(link / "run.json", {}, receipt_root=root)
    assert list(outside.iterdir()) == []


def test_terminal_receipt_rejects_parent_traversal(tmp_path: Path) -> None:
    """詞法parent traversal不藉resolve改變授權範圍。"""
    with pytest.raises(ValueError, match="parent_traversal"):
        receipt_writer.write_terminal_receipt(tmp_path / "x" / ".." / "run.json", {})
    assert not (tmp_path / "run.json").exists()
