import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


pytest_plugins = (
    "tests.fixtures.portfolio_ml_ooc_support",
    "tests.fixtures.ml_allocation_training_support",
)


@pytest.fixture(autouse=True)
def isolate_installed_formal_runtime_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Keep unit fixtures independent from the deployed candidate binding.

    The real Task Scheduler process must read the repository's active binding;
    pytest fixtures intentionally exercise temporary configs and must not
    inherit that production v6 map.  Tests that specifically validate binding
    loading set ``FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE`` to their own path.
    """

    from data_module import formal_runtime_config

    monkeypatch.setattr(
        formal_runtime_config,
        "DEFAULT_RUNTIME_ENVIRONMENT_FILE",
        tmp_path / "no-installed-runtime-binding.json",
    )
    monkeypatch.delenv("FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE", raising=False)


@pytest.fixture
def isolated_formal_runtime_subprocess_env(tmp_path: Path) -> dict[str, str]:
    """Give runtime-loading subprocess tests an explicit fail-closed binding.

    A subprocess does not see the module-level monkeypatch above.  Pointing it
    at a unique, missing path under repository ``output`` prevents a test
    process from accidentally loading the active deployed binding while still
    exercising the production path validation rules.
    """

    repository_root = Path(__file__).resolve().parents[1]
    isolated_binding = (
        repository_root
        / "output"
        / "v4_next_formal"
        / f".missing-subprocess-binding-{tmp_path.name[-8:]}.json"
    )
    environment = os.environ.copy()
    for name in (
        "FORMAL_DAILY_RUNTIME_CONFIG",
        "FORMAL_DAILY_RUNTIME_CONFIG_ROOT",
        "FORMAL_DAILY_ROLLING_CALENDAR_BUNDLE",
        "FORMAL_DAILY_PORTFOLIO_CLOCK_MANIFEST",
    ):
        environment.pop(name, None)
    environment["FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE"] = str(isolated_binding)
    return environment


@pytest.fixture(scope="session")
def sample_market_data() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", "2024-01-10")
    close = np.arange(100, 110, dtype=float)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close - 1,
            "high": close + 2,
            "low": close - 2,
            "close": close,
            "volume": np.arange(1_000_000, 1_000_010, dtype=np.int64),
        }
    )


@pytest.fixture(scope="session")
def sample_stock_data() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", "2024-01-10")
    rows = []
    for stock_index, stock_id in enumerate(("2330", "2317", "2412")):
        for day_index, date in enumerate(dates):
            close = float(100 + stock_index * 20 + day_index)
            rows.append(
                {
                    "date": date,
                    "stock_id": stock_id,
                    "open": close - 1,
                    "high": close + 2,
                    "low": close - 2,
                    "close": close,
                    "volume": 1_000_000 + stock_index * 10_000 + day_index,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture(scope="session")
def sample_index_data() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", "2024-01-10")
    rows = []
    for index_name in ["半導體", "電子", "金融"]:
        for day_index, date in enumerate(dates):
            rows.append(
                {
                    "date": date,
                    "index_name": index_name,
                    "value": 1_000 + day_index,
                    "change": day_index,
                    "change_pct": day_index / 100,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def test_config(tmp_path):
    from data_module.config import TWStockConfig

    return TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        profile="prod",
    )


def _report_qt_session_cleanup_error(session, message: str) -> None:
    """把未能安全清理 Qt 視窗的狀態保留為明確 QA 失敗。"""

    terminal_reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if terminal_reporter is not None:
        terminal_reporter.write_sep("!", f"Qt session cleanup QA ERROR: {message}", red=True)
    else:
        print(f"Qt session cleanup QA ERROR: {message}", file=sys.stderr)
    if session.exitstatus in (None, pytest.ExitCode.OK):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus) -> None:
    """在測試及 session fixture 結束後清理已存在的 WebEngine 視窗。"""

    del exitstatus
    # 只檢查測試已載入的 Qt 模組，不從 teardown 路徑建立 QApplication 或
    # 載入 UI startup 模組。沒有 Qt 應用程式時，這個 hook 不介入測試程序。
    widgets_module = sys.modules.get("PySide6.QtWidgets")
    core_module = sys.modules.get("PySide6.QtCore")
    webengine_module = sys.modules.get("PySide6.QtWebEngineWidgets")
    if widgets_module is None or core_module is None or webengine_module is None:
        return

    application_type = getattr(widgets_module, "QApplication", None)
    if not callable(application_type):
        _report_qt_session_cleanup_error(
            session,
            "PySide6.QtWidgets 已載入，但 QApplication 型別不可用；無法確認應用程式狀態。",
        )
        return

    try:
        app = application_type.instance()
    except Exception as exc:
        _report_qt_session_cleanup_error(
            session,
            f"無法檢查已載入的 QApplication: {type(exc).__name__}: {exc}",
        )
        return
    if app is None:
        return

    webengine_view_type = getattr(webengine_module, "QWebEngineView", None)
    thread_type = getattr(core_module, "QThread", None)
    if not callable(webengine_view_type) or not callable(thread_type):
        _report_qt_session_cleanup_error(
            session,
            "既有 QApplication 存在，但 QWebEngineView/QThread 型別不可用；保留所有視窗。",
        )
        return

    main_module = sys.modules.get("ui_qt.main")
    if main_module is None:
        # 單獨執行未載入主程式的 view 測試時，不在 teardown 新增 startup import。
        # 這種路由不會執行清理，必須從輸出明確看見此限制。
        terminal_reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        note = "Qt session cleanup 未執行：ui_qt.main 尚未載入，為避免 teardown startup import 而保留原視窗。"
        if terminal_reporter is not None:
            terminal_reporter.write_line(note)
        else:
            print(note, file=sys.stderr)
        return

    drain_deferred_deletes = getattr(main_module, "_drain_qt_deferred_deletes", None)
    if not callable(drain_deferred_deletes):
        _report_qt_session_cleanup_error(
            session,
            "ui_qt.main 已載入，但既有 _drain_qt_deferred_deletes 不可用；保留所有視窗。",
        )
        return

    shiboken_module = sys.modules.get("shiboken6")
    is_valid_qobject = getattr(shiboken_module, "isValid", None)
    get_cpp_pointer = getattr(shiboken_module, "getCppPointer", None)
    if not callable(is_valid_qobject) or not callable(get_cpp_pointer):
        _report_qt_session_cleanup_error(
            session,
            "shiboken6 無法確認 QObject 身分與有效性；保留所有視窗。",
        )
        return

    def qobject_key(obj) -> int:
        if not is_valid_qobject(obj):
            raise RuntimeError("QObject wrapper 已失效")
        pointers = get_cpp_pointer(obj)
        if not pointers or int(pointers[0]) <= 0:
            raise RuntimeError("QObject native identity 不明")
        return int(pointers[0])

    try:
        top_level_widgets = tuple(app.topLevelWidgets())
        top_level_keys = {qobject_key(widget) for widget in top_level_widgets}
        root_windows = []
        root_keys = set()

        for widget in top_level_widgets:
            widget_key = qobject_key(widget)
            parent = widget.parent()
            visited_parent_keys = set()
            has_top_level_owner = False
            while parent is not None:
                parent_key = qobject_key(parent)
                if parent_key in visited_parent_keys:
                    raise RuntimeError("QObject parent chain 出現循環")
                visited_parent_keys.add(parent_key)
                if parent_key in top_level_keys:
                    has_top_level_owner = True
                    break
                parent = parent.parent()
            if has_top_level_owner or widget_key in root_keys:
                continue

            webengine_views = tuple(widget.findChildren(webengine_view_type))
            if isinstance(widget, webengine_view_type):
                webengine_views = (widget, *webengine_views)
            if webengine_views:
                root_windows.append((widget, webengine_views))
                root_keys.add(widget_key)
    except Exception as exc:
        _report_qt_session_cleanup_error(
            session,
            f"無法安全盤點 Qt 視窗所有權: {type(exc).__name__}: {exc}；未關閉或刪除任何視窗。",
        )
        return

    if not root_windows:
        return

    worker_module = sys.modules.get("ui_qt.workers.task_worker")
    running_task_workers = getattr(worker_module, "running_task_workers", None)
    if not callable(running_task_workers):
        _report_qt_session_cleanup_error(
            session,
            "有 WebEngine 視窗，但全域 TaskWorker registry 未載入或不可用；未關閉或刪除任何視窗。",
        )
        return

    def running_owned_qthreads() -> tuple[object, ...]:
        managed_workers = tuple(running_task_workers())
        qthreads = {}
        for worker in managed_workers:
            key = qobject_key(worker)
            qthreads[key] = worker
        for parent in (app, *top_level_widgets):
            for thread in parent.findChildren(thread_type):
                key = qobject_key(thread)
                qthreads[key] = thread
        running = []
        for thread in qthreads.values():
            checker = getattr(thread, "isRunning", None)
            if not callable(checker):
                raise RuntimeError("QThread isRunning 狀態不可用")
            if checker():
                running.append(thread)
        return tuple(running)

    try:
        active_before_close = running_owned_qthreads()
    except Exception as exc:
        _report_qt_session_cleanup_error(
            session,
            f"無法確認全域 TaskWorker/QThread 狀態: {type(exc).__name__}: {exc}；未關閉或刪除任何視窗。",
        )
        return
    if active_before_close:
        _report_qt_session_cleanup_error(
            session,
            f"仍有 {len(active_before_close)} 個 TaskWorker/QThread 執行中；未關閉或刪除任何視窗。",
        )
        return

    closed_roots = []
    try:
        for window, _webengine_views in root_windows:
            if not is_valid_qobject(window):
                raise RuntimeError("WebEngine 根視窗在關閉前已失效")
            if not bool(window.close()):
                raise RuntimeError("WebEngine 根視窗拒絕 close()；保留 QObject 且不執行 deferred-delete drain")
            if bool(window.isVisible()):
                raise RuntimeError("WebEngine 根視窗 close() 後仍可見；保留 QObject 且不執行 deferred-delete drain")
            closed_roots.append(window)

        active_after_close = running_owned_qthreads()
        if active_after_close:
            raise RuntimeError(
                f"close() 後出現 {len(active_after_close)} 個執行中 TaskWorker/QThread；不執行 deferred-delete drain"
            )
    except Exception as exc:
        _report_qt_session_cleanup_error(
            session,
            f"WebEngine 根視窗未全部安全關閉: {type(exc).__name__}: {exc}；不執行 deferred-delete drain。",
        )
        return

    try:
        drain_deferred_deletes(app, tuple(closed_roots))
        residual_objects = []
        for window, webengine_views in root_windows:
            if is_valid_qobject(window):
                residual_objects.append("root window")
            if any(is_valid_qobject(view) for view in webengine_views):
                residual_objects.append("QWebEngineView descendant")
        if residual_objects:
            raise RuntimeError(
                "deferred-delete drain 後仍有有效 QObject: " + ", ".join(residual_objects)
            )
    except Exception as exc:
        _report_qt_session_cleanup_error(
            session,
            f"既有 deferred-delete drain 未完成: {type(exc).__name__}: {exc}。",
        )
        return

    terminal_reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    message = (
        f"Qt session cleanup: 已釋放 {len(closed_roots)} 個 WebEngine 根視窗，"
        f"共 {sum(len(views) for _window, views in root_windows)} 個 QWebEngineView。"
    )
    if terminal_reporter is not None:
        terminal_reporter.write_line(message)
    else:
        print(message, file=sys.stderr)
