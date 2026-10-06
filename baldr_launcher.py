"""Baldr 共用入口；Python 與 exe 以相同設定啟動。"""
from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
import runpy
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app_module.application_bootstrap import ApplicationSettings


def initialize_application() -> ApplicationSettings:
    from app_module.application_bootstrap import resolve_application_settings, apply_application_settings
    settings = resolve_application_settings()
    apply_application_settings(settings)
    home = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "baldr"
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            try:
                stream = os.fdopen(os.dup(1 if name == "stdout" else 2), "w",
                                   encoding="utf-8", errors="backslashreplace", buffering=1)
            except OSError:
                home.mkdir(parents=True, exist_ok=True)
                stream = (home / f"{name}.log").open("a", encoding="utf-8", buffering=1)
            setattr(sys, name, stream)
        elif hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass
    return settings


def configure_portable() -> tuple[Path, bool]:
    """保留既有 CLI 相容契約；解析與套用只有一個實作。"""
    settings = initialize_application()
    return settings.config_path, settings.configured


def main() -> int:
    # 必須早於 Qt/scipy 匯入，保留 Windows frozen spawn 分流。
    multiprocessing.freeze_support()
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    settings = initialize_application()
    from app_module.build_identity import detect_build_identity
    identity = detect_build_identity(repository_root=root)
    args = sys.argv[1:]
    while args and args[0] in ("-u", "-B", "-s", "-S"):
        args.pop(0)
    if args and args[0] == "-c":
        if len(args) < 2:
            raise ValueError("-c 缺少程式內容")
        sys.argv = ["-c", *args[2:]]
        exec(compile(args[1], "<baldr-cli>", "exec"), {"__name__": "__main__"})
        return 0
    if args and args[0] == "-m":
        if len(args) < 2:
            raise ValueError("-m 缺少模組名稱")
        sys.argv = [args[1], *args[2:]]
        runpy.run_module(args[1], run_name="__main__", alter_sys=True)
        return 0
    if args and args[0].endswith(".py"):
        script = Path(args[0])
        if not script.is_absolute():
            script = root / script
        sys.argv = [str(script), *args[1:]]
        runpy.run_path(str(script), run_name="__main__")
        return 0
    if args == ["--version"]:
        print(identity.display_text + " / Python " + sys.version.split()[0])
        return 0
    if args == ["--launch-info"]:
        print(json.dumps({"build": identity.to_dict(), "settings": settings.to_dict()}, ensure_ascii=False))
        return 0
    if args:
        raise ValueError("使用 Baldr、--version、--launch-info、-m 模組或 scripts/...py")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtGui import QIcon
    from ui_qt.startup_view import StartupController, StartupCancelled, set_windows_app_identity
    set_windows_app_identity()
    existing_app = QApplication.instance()
    if existing_app is not None and not isinstance(existing_app, QApplication):
        raise RuntimeError("GUI 啟動需要 QApplication")
    app = existing_app if isinstance(existing_app, QApplication) else QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(settings.resource_root / "ui_qt" / "app_icon.png")))
    startup = StartupController(app, settings.resource_root / "ui_qt")
    try:
        startup.preload()
        from ui_qt import main as qt_main
        startup.check_cancel()
    except StartupCancelled:
        startup.dismiss()
        return 0
    except Exception:
        startup.dismiss()
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            home = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "baldr"
            QMessageBox.critical(None, "baldr 啟動失敗", f"請查看 {home}/stderr.log")
        raise
    try:
        return int(qt_main.main(application_settings=settings, build_identity=identity,
                                startup_controller=startup))
    finally:
        startup.dismiss()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        import traceback
        error = traceback.format_exc()
        if sys.stderr is not None:
            sys.stderr.write(error)
            sys.stderr.flush()
        else:
            home = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "baldr"
            home.mkdir(parents=True, exist_ok=True)
            (home / "startup_error.log").write_text(error, encoding="utf-8")
        raise SystemExit(1)
