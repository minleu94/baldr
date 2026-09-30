"""以正式 UI 啟動流程驗證主視窗自然關閉與程序退出。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Lock, Timer, current_thread
import time
from typing import Any
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "output" / "qa" / "ui_shutdown_20260930"
DEFAULT_TIMEOUT_SECONDS = 90.0
SLOW_READ_SCENARIOS = frozenset(
    {"slow_workbench_read", "slow_research_console_read"}
)
_CHILD_MODE_ENV = "BALDR_UI_NATURAL_SHUTDOWN_CHILD"
_RECEIPT_ENV = "BALDR_UI_NATURAL_SHUTDOWN_RECEIPT"
_PROGRESS_ENV = "BALDR_UI_NATURAL_SHUTDOWN_PROGRESS"
_DELAY_ENV = "BALDR_UI_NATURAL_SHUTDOWN_CLOSE_DELAY_MS"
_SCENARIO_ENV = "BALDR_UI_NATURAL_SHUTDOWN_SCENARIO"
_SLOW_READ_ENV = "BALDR_UI_NATURAL_SHUTDOWN_SLOW_READ_MS"
_POLICY_CONFIG_ENV = "BALDR_UI_NATURAL_SHUTDOWN_POLICY_CONFIG"

_ISOLATED_PATH_ENVIRONMENTS = (
    "RESEARCH_CONSOLE_PROJECTION",
    "P0_SOURCE_CONTROL_CENTER_AUDIT",
    "P0_SOURCE_CONTROL_CENTER_DECISIONS",
    "P0_SOURCE_CONTROL_CENTER_LICENSE_EVIDENCE",
    "PROGRAM_READINESS_ARTIFACT",
    "MONTHLY_REVENUE_AVAILABILITY_CANDIDATE",
    "DATA_UPDATE_STATUS_ARTIFACT",
    "DATA_FRESHNESS_STATUS_ARTIFACT",
    "DATA_UPDATE_HISTORY_ARTIFACT",
    "TPEX_REFRESH_STATUS_ARTIFACT",
    "EVIDENCE_REHEARSAL_REPORT",
    "FORMAL_DAILY_RUNTIME_CONFIG",
    "FORMAL_DAILY_RUNTIME_CONFIG_ROOT",
    "FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE",
    "FORMAL_DAILY_PORTFOLIO_CLOCK_MANIFEST",
    "PIT_TAXONOMY_SOURCE_CONFIG",
    "PAPER_EQUAL_WEIGHT_BENCHMARK_PATH",
    "PAPER_TRADE_LEDGER_PATH",
    "WEEKLY_EVIDENCE_HISTORY_PROJECTION_PATH",
    "PIT_SECTOR_MEMBERSHIP_PATH",
    "PIT_SECTOR_MEMBERSHIP_RAW_ROOT",
    "PIT_SECTOR_MEMBERSHIP_CLOCK_MANIFEST_PATH",
    "PIT_SECTOR_MEMBERSHIP_UNIVERSE_SYMBOLS_PATH",
    "PIT_SECTOR_MEMBERSHIP_UNIVERSE_IDENTITY_PATH",
    "PIT_SECTOR_MEMBERSHIP_TAXONOMY_IDENTITY_PATH",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def build_isolated_child_environment(
    run_dir: Path,
    inherited: dict[str, str] | None = None,
    *,
    close_delay_ms: int = 2_500,
    scenario: str = "production_main_idle_startup_close",
    slow_read_ms: int = 500,
) -> dict[str, str]:
    """把 App 資料、輸出、使用者設定與可選來源全部釘在 run directory。"""

    resolved_run_dir = run_dir.resolve()
    isolated_roots = {
        "data_root": resolved_run_dir / "data",
        "output_root": resolved_run_dir / "app_output",
        "profile_root": resolved_run_dir / "profile",
        "roaming_root": resolved_run_dir / "profile" / "roaming",
        "local_root": resolved_run_dir / "profile" / "local",
        "temp_root": resolved_run_dir / "temp",
        "disabled_root": resolved_run_dir / "disabled_sources",
        "formal_root": resolved_run_dir / "formal_runtime",
    }
    for path in isolated_roots.values():
        path.mkdir(parents=True, exist_ok=True)

    environment = dict(os.environ if inherited is None else inherited)
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "DATA_ROOT": str(isolated_roots["data_root"]),
            "OUTPUT_ROOT": str(isolated_roots["output_root"]),
            "PROFILE": "test",
            "APPDATA": str(isolated_roots["roaming_root"]),
            "LOCALAPPDATA": str(isolated_roots["local_root"]),
            "USERPROFILE": str(isolated_roots["profile_root"]),
            "TEMP": str(isolated_roots["temp_root"]),
            "TMP": str(isolated_roots["temp_root"]),
            "XDG_CONFIG_HOME": str(isolated_roots["roaming_root"]),
            "XDG_DATA_HOME": str(isolated_roots["local_root"]),
            "XDG_CACHE_HOME": str(isolated_roots["local_root"] / "cache"),
            _POLICY_CONFIG_ENV: str(
                isolated_roots["profile_root"] / "personal_use_policy.json"
            ),
            "FORMAL_DAILY_RUNTIME_CONFIG_ROOT": str(isolated_roots["formal_root"]),
            "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(
                isolated_roots["output_root"] / "recommendation_learning"
            ),
            "RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(
                isolated_roots["output_root"] / "recommendation_learning"
            ),
            _DELAY_ENV: str(close_delay_ms),
            _SCENARIO_ENV: scenario,
            _SLOW_READ_ENV: str(slow_read_ms),
        }
    )

    for name in _ISOLATED_PATH_ENVIRONMENTS:
        if name == "FORMAL_DAILY_RUNTIME_CONFIG_ROOT":
            continue
        environment[name] = str(isolated_roots["disabled_root"] / f"{name}.missing")
    return environment


def validate_natural_exit(
    *,
    child_returncode: int | None,
    timed_out: bool,
    termination_requested: bool,
    owned_descendants_naturally_exited: bool | None,
    receipt: dict[str, Any] | None,
) -> list[str]:
    """以獨立證據判斷自然退出；crash log 不替代 OS return code。"""

    errors: list[str] = []
    if timed_out:
        errors.append("child_process_timeout")
    if termination_requested:
        errors.append("child_process_termination_was_requested")
    if child_returncode != 0:
        errors.append(f"child_os_returncode_not_zero:{child_returncode}")
    if owned_descendants_naturally_exited is not True:
        errors.append("owned_descendants_did_not_naturally_exit")
    if receipt is None:
        errors.append("child_receipt_missing")
        return errors

    required_true = (
        "main_returned",
        "window_shown",
        "close_requested",
        "app_about_to_quit",
        "deferred_delete_drain_returned",
    )
    for key in required_true:
        if receipt.get(key) is not True:
            errors.append(f"child_receipt_{key}_not_true")
    if receipt.get("main_returncode") != 0:
        errors.append(
            f"child_main_returncode_not_zero:{receipt.get('main_returncode')}"
        )
    if receipt.get("app_exec_returncode") != 0:
        errors.append(
            f"child_app_exec_returncode_not_zero:{receipt.get('app_exec_returncode')}"
        )
    if receipt.get("window_cpp_valid_after_drain") is not False:
        errors.append("window_cpp_object_not_confirmed_deleted_after_drain")
    if receipt.get("close_event_accepted") is not True:
        errors.append("close_event_not_accepted")
    if receipt.get("close_request_count") != 1:
        errors.append(f"close_request_count_not_one:{receipt.get('close_request_count')}")
    if receipt.get("managed_workers_at_about_to_quit") != 0:
        errors.append(
            "managed_workers_remained_at_about_to_quit:"
            f"{receipt.get('managed_workers_at_about_to_quit')}"
        )
    if receipt.get("update_background_process_at_about_to_quit") is not False:
        errors.append(
            "update_background_process_not_confirmed_stopped_at_about_to_quit:"
            f"{receipt.get('update_background_process_at_about_to_quit')}"
        )
    if receipt.get("all_config_paths_isolated") is not True:
        errors.append("config_paths_not_confirmed_isolated")
    if receipt.get("watchdog_fired") is True:
        errors.append("child_watchdog_fired")
    if receipt.get("scenario") in SLOW_READ_SCENARIOS:
        if receipt.get("slow_read_call_count") != 1:
            errors.append(
                f"{receipt.get('scenario')}_call_count_not_one:{receipt.get('slow_read_call_count')}"
            )
        requested_ms = receipt.get("slow_read_requested_ms")
        heartbeat_gap_ms = receipt.get("heartbeat_max_gap_ms")
        close_delay_ms = receipt.get("close_request_delay_ms")
        close_call_ms = receipt.get("close_call_elapsed_ms")
        if not isinstance(requested_ms, (int, float)):
            errors.append("slow_read_duration_missing")
        else:
            responsiveness_limit_ms = max(100.0, float(requested_ms) * 0.5)
            if not isinstance(heartbeat_gap_ms, (int, float)):
                errors.append("heartbeat_gap_missing")
            elif float(heartbeat_gap_ms) > responsiveness_limit_ms:
                errors.append(f"ui_heartbeat_gap_exceeded:{heartbeat_gap_ms:.1f}ms")
            if not isinstance(close_delay_ms, (int, float)):
                errors.append("close_request_delay_missing")
            elif float(close_delay_ms) > responsiveness_limit_ms:
                errors.append(f"close_request_delivery_delayed:{close_delay_ms:.1f}ms")
            if not isinstance(close_call_ms, (int, float)):
                errors.append("close_call_elapsed_missing")
            elif float(close_call_ms) > responsiveness_limit_ms:
                errors.append(f"close_call_blocked:{close_call_ms:.1f}ms")
    return errors


def _heartbeat_max_gap_ms(heartbeat_times: list[float], now: float) -> float:
    """Include both timer-to-timer gaps and the final interval before shutdown."""
    if not heartbeat_times:
        return 0.0
    gaps = [
        (later - earlier) * 1_000
        for earlier, later in zip(heartbeat_times, heartbeat_times[1:])
    ]
    gaps.append(max(0.0, (now - heartbeat_times[-1]) * 1_000))
    return max(gaps)


def _child_main() -> int:
    receipt_path = Path(os.environ[_RECEIPT_ENV]).resolve()
    progress_path = Path(os.environ[_PROGRESS_ENV]).resolve()
    close_delay_ms = max(0, int(os.environ.get(_DELAY_ENV, "2500")))
    scenario = os.environ.get(
        _SCENARIO_ENV,
        "production_main_idle_startup_close",
    )
    slow_read_ms = max(0, int(os.environ.get(_SLOW_READ_ENV, "500")))
    state: dict[str, Any] = {
        "schema_version": "ui-natural-shutdown-child.v1",
        "pid": os.getpid(),
        "started_at_utc": _utc_now(),
        "scenario": scenario,
        "main_returned": False,
        "main_returncode": None,
        "app_exec_returncode": None,
        "window_shown": False,
        "close_requested": False,
        "close_request_count": 0,
        "close_event_count": 0,
        "close_event_accepted": False,
        "app_about_to_quit": False,
        "deferred_delete_drain_called": False,
        "deferred_delete_drain_returned": False,
        "window_cpp_valid_after_drain": None,
        "watchdog_fired": False,
        "elapsed_seconds": None,
        "error": None,
    }
    progress_lock = Lock()

    def write_progress() -> None:
        with progress_lock:
            _write_json(progress_path, state)

    write_progress()

    try:
        import shiboken6
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication as QtApplication

        import ui_qt.crash_diagnostics as crash_diagnostics
        import ui_qt.main as app_main

        app_main._configure_console_streams()
        crash_log = crash_diagnostics.install_crash_diagnostics(
            os.environ["DATA_ROOT"]
        )
        app_main._crash_diagnostics_log_path = crash_log
        original_main_window = app_main.MainWindow
        original_drain = app_main._drain_qt_deferred_deletes
        original_workbench_inspect = app_main.WorkbenchSourceService.inspect
        original_research_console_inspect = app_main.ResearchConsoleSourceService.inspect
        started_at = time.monotonic()
        window_holder: dict[str, Any] = {}
        heartbeat_times: list[float] = []
        slow_read_release = Event()
        slow_read_timer: Timer | None = None

        if scenario in SLOW_READ_SCENARIOS:
            def delayed_inspect(original_inspect):
                def inspect(service: Any, *args: Any, **kwargs: Any) -> Any:
                    nonlocal slow_read_timer
                    if state.pop("slow_read_armed", False):
                        read_started = time.monotonic()
                        state["slow_read_call_count"] = int(
                            state.get("slow_read_call_count", 0)
                        ) + 1
                        state["slow_read_started_at"] = read_started
                        state["slow_read_thread_name"] = current_thread().name
                        state["slow_read_requested_ms"] = slow_read_ms
                        state["slow_read_active"] = True
                        write_progress()
                        slow_read_timer = Timer(
                            slow_read_ms / 1_000,
                            slow_read_release.set,
                        )
                        slow_read_timer.daemon = True
                        slow_read_timer.start()
                        released = slow_read_release.wait(
                            timeout=(slow_read_ms + 3_000) / 1_000
                        )
                        observed_ms = (time.monotonic() - read_started) * 1_000
                        state["slow_read_released"] = released
                        state["slow_read_observed_ms"] = observed_ms
                        state["slow_read_active"] = False
                        write_progress()
                    return original_inspect(service, *args, **kwargs)

                return inspect

            if scenario == "slow_workbench_read":
                app_main.WorkbenchSourceService.inspect = delayed_inspect(
                    original_workbench_inspect
                )
            else:
                app_main.ResearchConsoleSourceService.inspect = delayed_inspect(
                    original_research_console_inspect
                )

        class ProbeApplication(QtApplication):
            def exec(self) -> int:  # noqa: A003 - Qt event-loop API
                return_code = int(super().exec())
                state["app_exec_returncode"] = return_code
                _write_json(progress_path, state)
                return return_code

        class ProbeMainWindow(original_main_window):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                kwargs["policy_config_path"] = Path(os.environ[_POLICY_CONFIG_ENV])
                super().__init__(*args, **kwargs)
                window_holder["window"] = self
                state["main_window_initialized"] = True
                state["config_data_root"] = str(Path(self.config.data_root).resolve())
                state["config_output_root"] = str(Path(self.config.output_root).resolve())
                state["personal_policy_config_path"] = str(
                    Path(self.personal_policy_config_path).resolve()
                    if self.personal_policy_config_path is not None
                    else ""
                )
                run_dir = Path(receipt_path).parent.resolve()
                state["all_config_paths_isolated"] = all(
                    Path(value).resolve().is_relative_to(run_dir)
                    for value in (
                        state["config_data_root"],
                        state["config_output_root"],
                        state["personal_policy_config_path"],
                    )
                )
                state["managed_workers_after_startup"] = _running_worker_count()
                write_progress()

            def show(self) -> None:
                super().show()
                state["window_shown"] = True
                application = QtApplication.instance()
                if application is not None:
                    application.aboutToQuit.connect(self._record_about_to_quit)
                self._probe_show_monotonic = time.monotonic()
                self._close_due_monotonic = (
                    self._probe_show_monotonic + 0.150
                    if scenario in SLOW_READ_SCENARIOS
                    else self._probe_show_monotonic + close_delay_ms / 1_000
                )
                state["close_due_monotonic"] = self._close_due_monotonic
                self._heartbeat_timer = QTimer(self)
                self._heartbeat_timer.setInterval(10)
                self._heartbeat_timer.timeout.connect(self._record_heartbeat)
                self._heartbeat_timer.start()
                write_progress()
                if scenario == "slow_workbench_read":
                    QTimer.singleShot(100, self._trigger_slow_workbench_read)
                elif scenario == "slow_research_console_read":
                    QTimer.singleShot(100, self._trigger_slow_research_console_read)
                if scenario in SLOW_READ_SCENARIOS:
                    QTimer.singleShot(150, self._request_probe_close)
                    self._close_due_monotonic = self._probe_show_monotonic + 0.150
                else:
                    QTimer.singleShot(close_delay_ms, self._request_probe_close)
                    self._close_due_monotonic = (
                        self._probe_show_monotonic + close_delay_ms / 1_000
                    )

            def _record_heartbeat(self) -> None:
                heartbeat_times.append(time.monotonic())
                state["heartbeat_count"] = len(heartbeat_times)
                if len(heartbeat_times) > 1:
                    gap_ms = (heartbeat_times[-1] - heartbeat_times[-2]) * 1_000
                    state["heartbeat_max_gap_ms"] = max(
                        gap_ms,
                        float(state.get("heartbeat_max_gap_ms", 0.0)),
                    )

            def _trigger_slow_workbench_read(self) -> None:
                state["slow_probe_triggered"] = True
                state["slow_read_armed"] = True
                state["slow_probe_triggered_at"] = time.monotonic()
                write_progress()
                workbench_view = getattr(self, "workbench_view", None)
                refresh = getattr(workbench_view, "refresh_dashboard", None)
                if not callable(refresh):
                    state["slow_probe_error"] = "workbench_refresh_dashboard_missing"
                    write_progress()
                    return
                refresh()
                state["slow_probe_refresh_returned"] = True
                state["slow_probe_refresh_returned_at"] = time.monotonic()
                write_progress()

            def _trigger_slow_research_console_read(self) -> None:
                state["slow_probe_triggered"] = True
                state["slow_read_armed"] = True
                state["slow_probe_triggered_at"] = time.monotonic()
                write_progress()
                workbench_view = getattr(self, "workbench_view", None)
                research_view = getattr(workbench_view, "research_console_view", None)
                subtabs = getattr(workbench_view, "subtabs", None)
                if research_view is None or subtabs is None:
                    state["slow_probe_error"] = "research_console_subtab_missing"
                    write_progress()
                    return
                tab_index = subtabs.indexOf(research_view)
                if tab_index < 0:
                    state["slow_probe_error"] = "research_console_subtab_not_registered"
                    write_progress()
                    return
                subtabs.setCurrentIndex(tab_index)
                ensure_loaded = getattr(research_view, "ensure_loaded", None)
                if not callable(ensure_loaded):
                    state["slow_probe_error"] = "research_console_ensure_loaded_missing"
                    write_progress()
                    return
                ensure_loaded()
                state["slow_probe_refresh_returned"] = True
                state["slow_probe_refresh_returned_at"] = time.monotonic()
                write_progress()

            def _request_probe_close(self) -> None:
                state["close_requested"] = True
                state["close_request_count"] = int(state["close_request_count"]) + 1
                state["close_requested_elapsed_seconds"] = time.monotonic() - started_at
                state["close_request_delay_ms"] = max(
                    0.0,
                    (time.monotonic() - self._close_due_monotonic) * 1_000,
                )
                state["managed_workers_at_close_request"] = _running_worker_count()
                state["update_background_process_at_close_request"] = (
                    _update_process_running(self)
                )
                write_progress()
                close_call_started = time.monotonic()
                self.close()
                state["close_call_elapsed_ms"] = (
                    time.monotonic() - close_call_started
                ) * 1_000
                state["visible_after_close_call"] = bool(self.isVisible())
                write_progress()

            def _record_about_to_quit(self) -> None:
                state["app_about_to_quit"] = True
                state["managed_workers_at_about_to_quit"] = _running_worker_count()
                state["update_background_process_at_about_to_quit"] = (
                    _update_process_running(self)
                )
                if heartbeat_times:
                    state["heartbeat_max_gap_ms"] = max(
                        float(state.get("heartbeat_max_gap_ms", 0.0)),
                        _heartbeat_max_gap_ms(heartbeat_times, time.monotonic()),
                    )
                self._heartbeat_timer.stop()
                write_progress()

            def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
                state["close_event_count"] = int(state["close_event_count"]) + 1
                state["slow_read_active_at_close_event"] = bool(
                    state.get("slow_read_active", False)
                )
                if scenario in SLOW_READ_SCENARIOS:
                    slow_read_release.set()
                    state["slow_read_release_sent_by_close"] = True
                state["managed_workers_at_close_event"] = _running_worker_count()
                state["update_background_process_at_close_event"] = (
                    _update_process_running(self)
                )
                super().closeEvent(event)
                state["close_event_accepted"] = bool(event.isAccepted())
                write_progress()

        def tracked_deferred_delete_drain(app: Any, windows: tuple[Any, ...]) -> None:
            state["deferred_delete_drain_called"] = True
            write_progress()
            original_drain(app, windows)
            state["deferred_delete_drain_returned"] = True
            window = window_holder.get("window")
            state["window_cpp_valid_after_drain"] = (
                bool(shiboken6.isValid(window)) if window is not None else None
            )
            write_progress()

        app_main.QApplication = ProbeApplication
        app_main.MainWindow = ProbeMainWindow
        app_main._drain_qt_deferred_deletes = tracked_deferred_delete_drain
        main_returncode = int(app_main.main())
        state["main_returned"] = True
        state["main_returncode"] = main_returncode
        state["elapsed_seconds"] = time.monotonic() - started_at
        window = window_holder.get("window")
        if window is not None:
            try:
                state["window_cpp_valid_after_main"] = bool(shiboken6.isValid(window))
            except RuntimeError as exc:
                state["window_cpp_valid_after_main_error"] = str(exc)
        if slow_read_timer is not None:
            slow_read_timer.cancel()
            slow_read_timer.join(timeout=1.0)
        returncode = main_returncode
    except BaseException as exc:  # noqa: BLE001 - persist subprocess failure evidence
        state["error"] = f"{type(exc).__name__}: {exc}"
        state["exception_type"] = type(exc).__name__
        state["elapsed_seconds"] = None
        returncode = 1
    finally:
        state["finished_at_utc"] = _utc_now()
        write_progress()
        _write_json(receipt_path, state)
    return int(returncode)


def _configure_console_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                continue


def _running_worker_count() -> int | None:
    try:
        from ui_qt.workers.task_worker import running_task_workers

        return len(running_task_workers())
    except Exception:
        return None


def _update_process_running(window: Any) -> bool | None:
    update_view = getattr(window, "update_view", None)
    checker = getattr(update_view, "has_running_background_process", None)
    if not callable(checker):
        return None
    try:
        return bool(checker())
    except Exception:
        return None


def _process_descendants(pid: int) -> list[dict[str, Any]]:
    import psutil

    try:
        root = psutil.Process(pid)
        descendants = root.children(recursive=True)
    except psutil.NoSuchProcess:
        return []
    except psutil.AccessDenied as exc:
        raise RuntimeError(f"cannot inspect owned process tree: {exc}") from exc

    observed: list[dict[str, Any]] = []
    for process in descendants:
        try:
            observed.append(
                {
                    "pid": int(process.pid),
                    "create_time": float(process.create_time()),
                    "ppid": int(process.ppid()),
                    "name": process.name(),
                }
            )
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as exc:
            raise RuntimeError(
                f"cannot inspect owned descendant {process.pid}: {exc}"
            ) from exc
    return observed


def _identity_alive(identity: dict[str, Any]) -> bool | None:
    import psutil

    try:
        process = psutil.Process(int(identity["pid"]))
        return abs(float(process.create_time()) - float(identity["create_time"])) < 0.01
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return None


def _monitor_child_tree(
    child: Any,
    *,
    timeout_seconds: float,
) -> tuple[int | None, bool, list[dict[str, Any]], list[dict[str, Any]], str | None]:
    from scripts import qa_run_research_journey_qt_subprocess as owned_runner

    deadline = time.monotonic() + timeout_seconds
    descendants_by_identity: dict[tuple[int, float], dict[str, Any]] = {}
    snapshot_error: str | None = None
    timed_out = False
    returncode: int | None = None
    while True:
        try:
            for entry in _process_descendants(int(child.pid)):
                descendants_by_identity[(int(entry["pid"]), float(entry["create_time"]))] = entry
        except Exception as exc:
            snapshot_error = f"{type(exc).__name__}: {exc}"
        returncode = child.poll()
        if returncode is not None:
            break
        if time.monotonic() >= deadline:
            timed_out = True
            returncode, _ = owned_runner._terminate_owned_child(child, 2.0)
            break
        time.sleep(0.05)

    observed = list(descendants_by_identity.values())
    descendant_deadline = time.monotonic() + 2.0
    while not timed_out and time.monotonic() < descendant_deadline:
        try:
            for entry in _process_descendants(int(child.pid)):
                descendants_by_identity[(int(entry["pid"]), float(entry["create_time"]))] = entry
        except Exception as exc:
            snapshot_error = snapshot_error or f"{type(exc).__name__}: {exc}"
        alive = [entry for entry in descendants_by_identity.values() if _identity_alive(entry)]
        if not alive:
            break
        time.sleep(0.05)
    observed = list(descendants_by_identity.values())
    alive_after_wait = [
        {**entry, "alive": _identity_alive(entry)} for entry in observed
    ]
    all_exited = snapshot_error is None and all(
        entry["alive"] is False for entry in alive_after_wait
    )
    return returncode, timed_out, observed, alive_after_wait, snapshot_error if not all_exited else None


def _tail(path: Path, *, lines: int = 60) -> str:
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


def _render_report(summary: dict[str, Any]) -> str:
    receipt = summary.get("child_receipt") or {}
    errors = summary.get("errors") or []
    lines = [
        "# UI 自然關閉 subprocess QA",
        "",
        f"- 狀態：`{summary.get('status')}`",
        f"- Case：`{summary.get('scenario')}`",
        f"- OS 子程序 return code：`{summary.get('child_os_returncode')}`",
        f"- app.exec return code：`{receipt.get('app_exec_returncode')}`",
        f"- MainWindow main() return code：`{receipt.get('main_returncode')}`",
        f"- 自然關閉事件已接受：`{receipt.get('close_event_accepted')}`",
        f"- DeferredDelete drain 完成：`{receipt.get('deferred_delete_drain_returned')}`",
        f"- QObject drain 後有效：`{receipt.get('window_cpp_valid_after_drain')}`",
        f"- 子程序逾時：`{summary.get('timed_out')}`",
        f"- owned descendants 自然退出：`{summary.get('owned_descendants_naturally_exited')}`",
        f"- 啟動時 managed workers：`{receipt.get('managed_workers_after_startup')}`",
        f"- aboutToQuit managed workers：`{receipt.get('managed_workers_at_about_to_quit')}`",
        f"- aboutToQuit update process：`{receipt.get('update_background_process_at_about_to_quit')}`",
        f"- 設定路徑均隔離：`{receipt.get('all_config_paths_isolated')}`",
        f"- 心跳最大間隔：`{receipt.get('heartbeat_max_gap_ms')} ms`",
        f"- close timer 延遲：`{receipt.get('close_request_delay_ms')} ms`",
        f"- 慢讀耗時：`{receipt.get('slow_read_observed_ms')} ms`",
        f"- Crash diagnostics SESSION_END（輔助證據）：`{summary.get('crash_session_end')}`",
        f"- 收據：`{summary.get('child_receipt_path')}`",
        f"- 子程序 log：`{summary.get('stdout_path')}`",
        "",
        "## Failures",
        "",
    ]
    lines.extend(f"- `{error}`" for error in errors) if errors else lines.append("- 無")
    lines.extend(["", "## 子程序最後輸出", "", "```text", summary.get("stdout_tail", ""), "```", ""])
    return "\n".join(lines)


def _run_supervisor(args: argparse.Namespace) -> int:
    _configure_console_streams()
    from scripts import qa_run_research_journey_qt_subprocess as owned_runner

    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError("shutdown QA requires psutil to verify OS process custody") from exc

    output_root = Path(args.output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = output_root / (
        f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    )
    run_dir.mkdir(parents=False, exist_ok=False)
    receipt_path = run_dir / "child_receipt.json"
    progress_path = run_dir / "child_progress.json"
    stdout_path = run_dir / "child_stdout.log"
    summary_path = run_dir / "summary.json"
    report_path = run_dir / "REPORT.md"
    child_environment = build_isolated_child_environment(
        run_dir,
        close_delay_ms=args.close_delay_ms,
        scenario=args.scenario,
        slow_read_ms=args.slow_read_ms,
    )
    child_environment.update(
        {
            _CHILD_MODE_ENV: "1",
            _RECEIPT_ENV: str(receipt_path),
            _PROGRESS_ENV: str(progress_path),
        }
    )
    process_tree = owned_runner._OwnedProcessTree()
    child: Any = None
    child_returncode: int | None = None
    timed_out = False
    observed_descendants: list[dict[str, Any]] = []
    descendants_alive_after_wait: list[dict[str, Any]] = []
    process_snapshot_error: str | None = None
    termination_requested = False
    tree_close_error: str | None = None
    child_handle_close_error: str | None = None
    started_at = _utc_now()
    command = [sys.executable, "-u", str(Path(__file__).resolve())]
    summary: dict[str, Any] = {
        "schema_version": "ui-natural-shutdown.v1",
        "status": "running",
        "scenario": args.scenario,
        "runner_pid": os.getpid(),
        "started_at_utc": started_at,
        "run_dir": str(run_dir),
        "command": command,
        "timeout_seconds": float(args.timeout_seconds),
        "child_os_returncode": None,
        "child_pid": None,
        "timed_out": False,
        "termination_requested": False,
        "owned_descendants_observed": [],
        "owned_descendants_naturally_exited": None,
        "process_snapshot_error": None,
        "tree_close_error": None,
        "child_handle_close_error": None,
        "receipt_path": str(receipt_path),
        "progress_path": str(progress_path),
        "stdout_path": str(stdout_path),
        "child_receipt": None,
        "crash_session_end": None,
        "errors": [],
    }
    _write_json(summary_path, summary)

    try:
        with stdout_path.open("wb") as output_handle:
            child = owned_runner._spawn_owned_child(
                command,
                cwd=PROJECT_ROOT,
                env=child_environment,
                log_handle=output_handle,
                owned_process_tree=process_tree,
            )
            summary["child_pid"] = int(child.pid)
            summary["process_tree_management"] = process_tree.management_mode
            summary["owned_process_tree_attached"] = process_tree.attached
            _write_json(summary_path, summary)
            (
                child_returncode,
                timed_out,
                observed_descendants,
                descendants_alive_after_wait,
                process_snapshot_error,
            ) = _monitor_child_tree(
                child,
                timeout_seconds=float(args.timeout_seconds),
            )
    except BaseException as exc:  # noqa: BLE001 - preserve bounded QA evidence
        summary["runner_error"] = f"{type(exc).__name__}: {exc}"
        if child is not None and child.poll() is None:
            termination_requested = True
            try:
                child_returncode, _ = owned_runner._terminate_owned_child(child, 2.0)
            except BaseException as terminate_exc:  # noqa: BLE001
                summary["runner_error"] += (
                    f"; termination {type(terminate_exc).__name__}: {terminate_exc}"
                )
    finally:
        termination_requested = termination_requested or timed_out
        if child is not None and child_returncode is None:
            child_returncode = child.poll()
        try:
            process_tree.close()
        except BaseException as exc:  # noqa: BLE001 - retain cleanup evidence
            tree_close_error = f"{type(exc).__name__}: {exc}"
        if child is not None:
            close_child = getattr(child, "close", None)
            if callable(close_child):
                try:
                    close_child()
                except BaseException as exc:  # noqa: BLE001
                    child_handle_close_error = f"{type(exc).__name__}: {exc}"

    child_receipt: dict[str, Any] | None = None
    if receipt_path.exists():
        try:
            child_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            process_snapshot_error = process_snapshot_error or (
                f"child_receipt_invalid:{type(exc).__name__}:{exc}"
            )
    data_root = Path(child_environment["DATA_ROOT"])
    crash_log = data_root / "logs" / "ui_qt_crash.log"
    crash_text = crash_log.read_text(encoding="utf-8", errors="replace") if crash_log.exists() else ""
    crash_session_end = any(line.startswith("SESSION_END ") for line in crash_text.splitlines())
    descendants_natural = (
        process_snapshot_error is None
        and all(entry.get("alive") is False for entry in descendants_alive_after_wait)
    )
    errors = validate_natural_exit(
        child_returncode=child_returncode,
        timed_out=timed_out,
        termination_requested=termination_requested,
        owned_descendants_naturally_exited=descendants_natural,
        receipt=child_receipt,
    )
    if process_snapshot_error is not None:
        errors.append(f"process_snapshot_error:{process_snapshot_error}")
    if tree_close_error is not None:
        errors.append(f"owned_process_tree_close_error:{tree_close_error}")
    if child_handle_close_error is not None:
        errors.append(f"child_handle_close_error:{child_handle_close_error}")
    errors.extend(
        f"child_error:{receipt_error}"
        for receipt_error in ((child_receipt or {}).get("error"),)
        if receipt_error
    )
    summary.update(
        {
            "status": "passed" if not errors else "failed",
            "ended_at_utc": _utc_now(),
            "child_os_returncode": child_returncode,
            "timed_out": timed_out,
            "termination_requested": termination_requested,
            "owned_descendants_observed": observed_descendants,
            "owned_descendants_after_wait": descendants_alive_after_wait,
            "owned_descendants_naturally_exited": descendants_natural,
            "process_snapshot_error": process_snapshot_error,
            "tree_close_error": tree_close_error,
            "child_handle_close_error": child_handle_close_error,
            "child_receipt": child_receipt,
            "child_receipt_path": str(receipt_path),
            "crash_diagnostics_log": str(crash_log),
            "crash_session_end": crash_session_end,
            "stdout_tail": _tail(stdout_path),
            "errors": errors,
        }
    )
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary), encoding="utf-8")
    print(
        f"UI natural shutdown status={summary['status']} "
        f"child_os_returncode={child_returncode} timed_out={timed_out} "
        f"summary={summary_path} report={report_path}"
    )
    return 0 if summary["status"] == "passed" else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--close-delay-ms", type=int, default=2_500)
    parser.add_argument(
        "--scenario",
        choices=(
            "production_main_idle_startup_close",
            "slow_workbench_read",
            "slow_research_console_read",
        ),
        default="production_main_idle_startup_close",
    )
    parser.add_argument("--slow-read-ms", type=int, default=500)
    args = parser.parse_args(argv)
    if args.timeout_seconds < 60:
        raise ValueError("production startup timeout must be at least 60 seconds")
    if args.close_delay_ms < 0:
        raise ValueError("close delay must be non-negative")
    if args.slow_read_ms < 50:
        raise ValueError("slow-read duration must be at least 50 milliseconds")
    return args


def main(argv: list[str] | None = None) -> int:
    if os.environ.get(_CHILD_MODE_ENV) == "1":
        return _child_main()
    return _run_supervisor(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
