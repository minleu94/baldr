import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QPushButton, QTableWidget

from app_module.storage_overview import StorageArtifact, StorageOverview
from ui_qt.views.storage_overview_view import StorageOverviewView
from ui_qt.workers.task_worker import running_task_workers


def app() -> QApplication:
    instance = QApplication.instance()
    return instance if instance is not None else QApplication(sys.argv)


def test_missing_inventory_status_names_path_and_does_not_claim_completion(tmp_path: Path) -> None:
    app()
    missing = tmp_path / "_internal" / "dist"
    view = StorageOverviewView({}, None, package_root=missing)
    view._apply(StorageOverview((), (), False, str(missing),
                               f"套件根不可用；未執行盤點：{missing}（路徑不存在）"))
    assert str(missing) in view.status_label.text()
    assert "盤點未完成" in view.status_label.text()
    assert "有界盤點完成" not in view.status_label.text()
    assert view._inventory_target() == str(missing)
    view.close()


def test_incomplete_package_size_is_marked_partial_and_tables_read_only(tmp_path: Path) -> None:
    app()
    package = tmp_path / "_internal"
    view = StorageOverviewView({}, None, package_root=package)
    overview = StorageOverview((), (StorageArtifact("_internal", 0, False,
        "含連結／重解析點；未跟隨，大小不完整，保留"),), False,
        str(package), "套件根有界盤點完成；含不可讀或未跟隨連結項，大小不完整", True)
    view._apply(overview)
    assert str(package) in view.status_label.text()
    assert "大小不完整" in view.status_label.text()
    assert view.artifacts_table.item(0, 1).text() == "0"
    assert view.artifacts_table.item(0, 2).text() == "否／部分"
    assert view.locations_table.editTriggers() == QTableWidget.NoEditTriggers
    assert view.artifacts_table.editTriggers() == QTableWidget.NoEditTriggers
    assert not any(any(word in button.text() for word in ("刪除", "清除", "移除"))
                   for button in view.findChildren(QPushButton))
    view.close()


def test_success_status_distinguishes_inventory_from_capacity_roots(tmp_path: Path) -> None:
    app()
    package = tmp_path / "_internal"
    package.mkdir()
    view = StorageOverviewView({}, None, package_root=package)
    view._apply(StorageOverview((), (StorageArtifact("_internal", 0, True,
        "已量測；引用與保留狀態尚未核對"),), False,
        str(package), "套件根有界盤點完成", True))
    assert str(package) in view.status_label.text()
    assert "清理須另行核對引用" in view.status_label.text()
    view.close()


def test_real_worker_refresh_can_repeat_after_native_cleanup(tmp_path: Path) -> None:
    application = app()
    package = tmp_path / "_internal"
    package.mkdir()
    asset = package / "module.bin"
    asset.write_bytes(b"a" * (1024 * 1024))
    view = StorageOverviewView({}, None, package_root=package)

    def wait_until(predicate, timeout_ms: int = 2500) -> bool:
        if predicate():
            return True
        loop = QEventLoop()
        poll = QTimer()
        deadline = QTimer()
        poll.setInterval(5)
        poll.timeout.connect(lambda: loop.quit() if predicate() else None)
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        poll.start()
        deadline.start(timeout_ms)
        loop.exec()
        poll.stop()
        deadline.stop()
        return predicate()

    try:
        view.refresh_button.click()
        assert wait_until(lambda: view._worker is None and view.refresh_button.isEnabled()
                          and not running_task_workers())
        assert view.artifacts_table.rowCount() == 1
        assert view.artifacts_table.item(0, 1).text() == "1"
        asset.write_bytes(b"b" * (2 * 1024 * 1024))
        view.refresh_button.click()
        assert wait_until(lambda: view._worker is None and view.refresh_button.isEnabled()
                          and not running_task_workers())
        assert view.artifacts_table.rowCount() == 1
        assert view.artifacts_table.item(0, 1).text() == "2"
        assert "有界盤點完成" in view.status_label.text()
    finally:
        view.request_close()
        view.close()
        assert wait_until(lambda: not running_task_workers())
        application.processEvents()
    assert running_task_workers() == ()
