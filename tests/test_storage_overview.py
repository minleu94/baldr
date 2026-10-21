from pathlib import Path
import os

import pytest

import app_module.storage_overview as storage_overview
from app_module.storage_overview import inspect_storage


def test_storage_reads_explicit_trials_without_mutation(tmp_path: Path) -> None:
    trial = tmp_path / "trials" / "rc1"
    trial.mkdir(parents=True)
    asset = trial / "app.bin"
    asset.write_bytes(b"preserve")
    result = inspect_storage({"資料": tmp_path, "缺件": tmp_path / "missing"}, trial.parent)
    assert result.locations[0].free_bytes is not None
    assert result.locations[1].free_bytes is None
    assert result.locations[1].name == "缺件"
    assert "路徑不存在" in result.locations[1].status
    assert result.artifacts[0].measured_bytes == 8
    assert result.artifacts[0].complete
    assert "保留" in result.artifacts[0].status
    assert "有界盤點完成" in result.inventory_status
    assert result.inventory_available
    assert result.inventory_path == str(trial.parent)
    assert asset.read_bytes() == b"preserve"


def test_missing_inventory_root_is_not_reported_as_empty_success(tmp_path: Path) -> None:
    missing = tmp_path / "dist"
    result = inspect_storage({}, missing)
    assert not result.artifacts
    assert result.inventory_path == str(missing)
    assert "未找到" in result.inventory_status
    assert "未執行盤點" in result.inventory_status
    assert not result.inventory_available


def test_inventory_root_file_is_reported_as_invalid(tmp_path: Path) -> None:
    root_file = tmp_path / "not-a-directory"
    root_file.write_text("file", encoding="utf-8")
    result = inspect_storage({}, root_file)
    assert result.inventory_path == str(root_file)
    assert "不是目錄" in result.inventory_status
    assert "未執行盤點" in result.inventory_status


def test_inventory_root_permission_failure_reports_path_and_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "dist"
    root.mkdir()
    original_scandir = os.scandir

    def denied(path):
        if Path(path) == root:
            raise PermissionError("fixture permission denied")
        return original_scandir(path)

    monkeypatch.setattr(storage_overview.os, "scandir", denied)
    result = inspect_storage({}, root)
    assert result.inventory_path == str(root)
    assert "不可用" in result.inventory_status
    assert str(root) in result.inventory_status
    assert "fixture permission denied" in result.inventory_status
    assert not result.artifacts


def test_unreadable_package_child_is_partial_not_zero_byte_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "_internal"
    package.mkdir()
    blocked = package / "module_dir"
    blocked.mkdir()
    original_scandir = os.scandir

    def denied(path):
        if Path(path) == blocked:
            raise PermissionError("fixture child denied")
        return original_scandir(path)

    monkeypatch.setattr(storage_overview.os, "scandir", denied)
    result = inspect_storage({}, None, package_root=package)
    assert result.inventory_available
    assert len(result.artifacts) == 1
    assert result.artifacts[0].measured_bytes == 0
    assert not result.artifacts[0].complete
    assert "不可讀" in result.artifacts[0].status
    assert "不完整" in result.inventory_status


def test_package_root_is_one_artifact_and_counts_root_files(tmp_path: Path) -> None:
    package = tmp_path / "_internal"
    package.mkdir()
    (package / "baldr.exe").write_bytes(b"exe")
    nested = package / "ui_qt"
    nested.mkdir()
    (nested / "main.pyc").write_bytes(b"module")
    result = inspect_storage({}, None, package_root=package)
    assert len(result.artifacts) == 1
    assert result.artifacts[0].name == "_internal"
    assert result.artifacts[0].measured_bytes == 9
    assert result.artifacts[0].complete
    assert result.inventory_path == str(package)
    assert "套件根有界盤點完成" in result.inventory_status


def test_incomplete_zero_byte_package_is_not_a_complete_empty_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "_internal"
    package.mkdir()
    linked = package / "linked"
    linked.mkdir()
    real_is_reparse = storage_overview._is_reparse
    monkeypatch.setattr(storage_overview, "_is_reparse",
                        lambda path, metadata: path == linked or real_is_reparse(path, metadata))
    result = inspect_storage({}, None, package_root=package)
    assert len(result.artifacts) == 1
    assert result.artifacts[0].measured_bytes == 0
    assert not result.artifacts[0].complete
    assert "未跟隨" in result.artifacts[0].status
    assert "不完整" in result.inventory_status
    assert result.inventory_available


def test_trial_limit_is_shared_and_marks_size_incomplete(tmp_path: Path) -> None:
    version = tmp_path / "trials" / "rc1"
    version.mkdir(parents=True)
    for index in range(4097):
        (version / str(index)).touch()
    result = inspect_storage({}, version.parent)
    assert result.limited
    assert len(result.artifacts) == 1
    assert not result.artifacts[0].complete
    assert "不完整" in result.artifacts[0].status
    assert "上限" in result.inventory_status


def test_trial_root_regular_entries_consume_shared_budget(tmp_path: Path) -> None:
    for index in range(4097):
        (tmp_path / f"file-{index}").touch()
    result = inspect_storage({}, tmp_path)
    assert result.limited
    assert not result.artifacts
    assert "上限" in result.inventory_status


def test_trial_versions_are_capped_at_64(tmp_path: Path) -> None:
    for index in range(65):
        (tmp_path / f"rc{index}").mkdir()
    result = inspect_storage({}, tmp_path)
    assert len(result.artifacts) == 64
    assert result.limited
    assert "64版本" in result.inventory_status


def test_inner_symlink_is_not_followed(tmp_path: Path) -> None:
    version = tmp_path / "trials" / "rc1"
    version.mkdir(parents=True)
    target = tmp_path / "private"
    target.mkdir()
    (target / "large.bin").write_bytes(b"private")
    try:
        (version / "linked").symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"此平台無法建立目錄連結：{exc}")
    result = inspect_storage({}, version.parent)
    assert result.artifacts[0].measured_bytes == 0
    assert not result.artifacts[0].complete
    assert "未跟隨" in result.artifacts[0].status


def test_storage_cancellation_stops_before_disk_read(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="已取消"):
        inspect_storage({"資料": tmp_path}, tmp_path, cancel_callback=lambda: True)
