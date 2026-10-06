"""載入 UI 的進度、資源與安全關閉契約。"""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication, QWidget
from ui_qt.startup_view import STAGES, StartupCancelled, StartupController, StartupView

ASSETS = Path(__file__).resolve().parents[1] / "ui_qt"

@pytest.fixture
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance
    instance.processEvents()

def test_original_resources_and_true_stage_progress(app):
    controller = StartupController(app, ASSETS)
    assert not controller.view.background.isNull()
    assert not controller.view.windowIcon().isNull()
    assert controller.view.progress.maximum() == 0
    window = QWidget()
    for position, label in enumerate(STAGES):
        controller.step(label)
        assert controller.view.progress.value() == position
        assert not window.isVisible()
    assert controller.view.progress.value() < controller.view.progress.maximum()
    controller.ready(window)
    assert window.isVisible() and window.isEnabled()
    assert controller.view.progress.value() == len(STAGES)
    assert not controller.view.isVisible()
    window.close()

def test_cancel_never_shows_main_or_completes_progress(app):
    controller = StartupController(app, ASSETS)
    window = QWidget()
    controller.view.close()
    with pytest.raises(StartupCancelled):
        controller.ready(window)
    assert not window.isVisible()
    assert not controller.view.isVisible()
    controller.dismiss()

def test_missing_background_and_no_click_dismiss(app, tmp_path):
    view = StartupView(tmp_path)
    view.show()
    assert view.background.isNull()
    assert view.label.text() and view.progress.maximum() == 0
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    QTest.mouseClick(view, Qt.MouseButton.LeftButton)
    assert view.isVisible() and not view.cancel_requested
    view.close()

def test_repeat_launch_and_monotonic_stages(app):
    for _ in range(2):
        controller = StartupController(app, ASSETS)
        controller.step(STAGES[2])
        with pytest.raises(ValueError):
            controller.step(STAGES[1])
        controller.dismiss()

def test_cancel_background_import_drains_thread(app, monkeypatch):
    import importlib
    import threading
    from PySide6.QtCore import QTimer
    controller = StartupController(app, ASSETS)
    original = importlib.import_module
    seen = []
    def record(name):
        seen.append(threading.current_thread().name)
        return original(name)
    monkeypatch.setattr(importlib, "import_module", record)
    QTimer.singleShot(0, controller.view.close)
    with pytest.raises(StartupCancelled):
        controller.preload()
    assert seen and set(seen) == {"baldr-imports"}
    assert not any(t.name == "baldr-imports" for t in threading.enumerate())
    controller.dismiss()
