"""可攜版入口；資料與明示設定保留於程式包之外。"""
from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import runpy
import sys


def configure_portable() -> tuple[Path, bool]:
    import json

    home = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "baldr"
    home.mkdir(parents=True, exist_ok=True)
    config_path = Path(os.environ.get("BALDR_CONFIG", str(home / "config.json")))
    configured = config_path.is_file()
    if configured:
        values = json.loads(config_path.read_text(encoding="utf-8"))
        allowed = {"DATA_ROOT", "OUTPUT_ROOT", "PERSONAL_DATA_ROOT", "PERSONAL_WATCHLIST_SOURCE",
                   "PERSONAL_JOURNAL_ROOT", "PERSONAL_JOURNAL_MODE", "PERSONAL_STORE_ROOT",
                   "PERSONAL_STORE_MODE", "PERSONAL_MODEL_POLICY_PATH"}
        if not isinstance(values, dict) or set(values) - allowed:
            raise ValueError("config.json 含未支援的設定")
        for key, value in values.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} 必須是非空字串")
            if key.endswith(("ROOT", "PATH", "SOURCE")) and not Path(value).is_absolute():
                raise ValueError(f"{key} 必須是絕對路徑")
            os.environ.setdefault(key, value)
    configured = configured or bool(os.environ.get("DATA_ROOT") and os.environ.get("OUTPUT_ROOT"))
    os.environ.setdefault("DATA_ROOT", str(home / "market"))
    os.environ.setdefault("OUTPUT_ROOT", str(home / "output"))
    package = Path(sys.executable).parent.resolve() if getattr(sys, "frozen", False) else Path(__file__).parent.resolve()
    for key in ("DATA_ROOT", "OUTPUT_ROOT"):
        path = Path(os.environ[key]).expanduser()
        if not path.is_absolute():
            raise ValueError(f"{key} 必須是絕對路徑")
        if getattr(sys, "frozen", False) and (path.resolve() == package or path.resolve().is_relative_to(package)):
            raise ValueError(f"{key} 必須放在程式包之外")
    os.environ.setdefault("MPLCONFIGDIR", str(Path(os.environ["OUTPUT_ROOT"]) / "application_state" / "matplotlib"))
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            # windowed bootloader 將 Python stream 設為 None；CLI 的 pipe
            # 若仍存在，沿原 handle 回傳 stdout JSON，不能改寫成 log。
            try:
                stream = os.fdopen(os.dup(1 if name == "stdout" else 2), "w",
                                   encoding="utf-8", errors="backslashreplace", buffering=1)
            except OSError:
                stream = (home / f"{name}.log").open("a", encoding="utf-8", buffering=1)
            setattr(sys, name, stream)
        elif hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    return config_path, configured


def main() -> int:
    # 在 Qt／scipy 匯入前分流 Windows spawn worker。
    multiprocessing.freeze_support()
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    sys.path.insert(0, str(root))
    config_path, configured = configure_portable()
    args = sys.argv[1:]
    while args and args[0] in ("-u", "-B", "-s", "-S"):
        args.pop(0)
    if args and args[0] == "-c":
        sys.argv = ["-c", *args[2:]]
        exec(compile(args[1], "<baldr-cli>", "exec"), {"__name__": "__main__"})
        return 0
    if args and args[0] == "-m":
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
        print("baldr portable 2026.10.06 / Python " + sys.version.split()[0])
        return 0
    if args:
        raise ValueError("使用 baldr.exe、--version、-m 模組或 scripts/...py")
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtGui import QIcon
    from ui_qt.startup_view import StartupController, StartupCancelled, set_windows_app_identity
    set_windows_app_identity()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(root / 'ui_qt' / 'app_icon.png')))
    startup = StartupController(app, root / 'ui_qt')
    try:
        startup.preload()
        from ui_qt import main as qt_main
        startup.check_cancel()
    except StartupCancelled:
        startup.dismiss()
        return 0
    except Exception:
        startup.dismiss()
        if os.environ.get('QT_QPA_PLATFORM') != 'offscreen':
            home = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'baldr'
            QMessageBox.critical(None, 'baldr 啟動失敗', f'請查看 {home}/stderr.log')
        raise
    qt_main._startup_controller = startup
    # 以既有 composition 的明示根定位可寫狀態，不改資料核驗器。
    state_root = Path(os.environ["OUTPUT_ROOT"]) / "application_state"
    qt_main.project_root = state_root
    registry_type = qt_main.CurrentRestatedMLRunRegistry
    research_state_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "baldr" / "research_state"
    qt_main.CurrentRestatedMLRunRegistry = lambda: registry_type(repository_root=research_state_root)
    window_type = qt_main.MainWindow
    class PortableWindow(window_type):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if not configured:
                QTimer.singleShot(250, self.show_setup)

        def show_setup(self) -> None:
            box = QMessageBox(self)
            box.setWindowTitle("baldr 首次資料設定")
            box.setText(f"目前使用空資料根：{os.environ['DATA_ROOT']}\n"
                        f"請在 {config_path} 明示 DATA_ROOT 與 OUTPUT_ROOT 後重開。\n"
                        "私人資料與模型請沿原設定成對選定；未設定不會自動啟用。")
            box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            box.show()
    qt_main.MainWindow = PortableWindow
    qt_main._crash_diagnostics_log_path = qt_main.install_crash_diagnostics()
    exit_code = qt_main.main()
    qt_main._startup_controller = None
    if exit_code and os.environ.get('QT_QPA_PLATFORM') != 'offscreen':
        error_app = QApplication.instance() or QApplication([])
        home = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'baldr'
        QMessageBox.critical(None, 'baldr 啟動失敗',
            f'主視窗未能建立。請保留 {home}/stdout.log 與 stderr.log 供排錯；不要重建或搬移資料。')
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # CLI／offscreen 錯誤必須回傳非零及 traceback，不交由 windowed
        # bootloader 彈出會阻塞背景排程的原生對話框。
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
