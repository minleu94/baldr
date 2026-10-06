"""隔離實際 launcher：載入進度、原資源、取消與正常關閉。"""
import json
from pathlib import Path
import sys
case = Path(sys.argv[1])
mode = sys.argv[2] if len(sys.argv) > 2 else "ready"
def guard(event, args):
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise PermissionError("離線 startup fixture 禁止 provider 網路")
sys.addaudithook(guard)
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from ui_qt import startup_view, main as qt_main
from ui_qt.workers.task_worker import running_task_workers
entry = sys._baldr_test_entry
result = {"mode": mode, "stages": [], "native": False}
original_controller = startup_view.StartupController
class Controller(original_controller):
    def step(self, label):
        if self.window is not None:
            assert not self.window.isVisible()
        if mode == "cancel" and label == startup_view.STAGES[7]:
            self.view.close()
        if mode == "failure" and label == startup_view.STAGES[11]:
            raise RuntimeError("fixture 初始化失敗，驗證合作式清理")
        super().step(label)
        result["stages"].append(label)
    def ready(self, window):
        assert self.view.progress.value() < self.view.progress.maximum()
        super().ready(window)
        result["ready"] = window.isVisible()
        result["original_icon"] = not window.windowIcon().isNull()
        result["background"] = not self.view.background.isNull()
        result["workspaces"] = len(window.workspace_widgets)
        QTimer.singleShot(500, close)
startup_view.StartupController = Controller
original_window = qt_main.MainWindow
class FixtureWindow(original_window):
    def __init__(self, **kwargs):
        kwargs["policy_config_path"] = case / "policy.json"
        super().__init__(**kwargs)
qt_main.MainWindow = FixtureWindow
def close():
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, QMessageBox):
            widget.close()
    qt_main._startup_controller.window.close()
sys.argv = ["baldr.exe"]
exit_code = entry.main()
assert exit_code == (1 if mode == "failure" else 0), exit_code
assert not running_task_workers(), "取消或關閉後仍有 worker"
if mode in ("cancel", "failure"):
    assert not result.get("ready"), result
else:
    assert result["ready"] and result["original_icon"] and result["background"]
    assert result["workspaces"] == 9 and len(result["stages"]) == len(startup_view.STAGES)
result.update(status="passed", exit=exit_code, frozen=getattr(sys, "frozen", False))
(case / "portable_startup_probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
