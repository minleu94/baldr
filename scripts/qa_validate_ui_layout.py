"""稽核真正 Qt MainWindow 各工作區的幾何、捲動與長內容可讀性。

此 runner 以 offscreen Qt 啟動正式組合的 MainWindow，但將 DATA_ROOT、
OUTPUT_ROOT、設定路徑與來源 projection 環境變數隔離到 ignored QA 輸出。
所有資料表替換都使用短暫合成 model，並在離開 context 時還原原 model；
runner 不點擊更新、推薦、回測、保存或其他服務按鈕。

2293x912 是本機 2293x960 logical display 扣除工作列後的最大化可用 client
geometry。offscreen runner 會用相同 logical size 量測，並在報告中標明這是
最大化尺寸模擬，不宣稱量到 Windows 原生視窗框或實體顯示器邊界。
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import faulthandler
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Iterator, TextIO


DEFAULT_SCALES = ("1", "1.5")
GEOMETRIES: dict[str, tuple[int, int, str]] = {
    "default": (1400, 800, "預設視窗"),
    "compact": (1366, 768, "一般桌面視窗"),
    "actual_max": (2293, 912, "最大化可用尺寸模擬"),
}
EXPECTED_WORKSPACES = (
    "workbench",
    "market_explore",
    "recommendation",
    "backtest",
    "watchlist",
    "stock_research",
    "portfolio",
    "update",
    "runtime",
)
SYNTHETIC_ROW_COUNT = 60
LONG_CELL_TEXT = (
    "隔離版版面稽核合成說明：這段較長的完整內容用來確認表格欄位可以透過水平捲動到達，"
    "並檢查 TooltipRole 是否保留完整文字；資料不代表任何真實股票、策略或正式來源。"
)
LONG_HEADER_TEXT = "完整來源脈絡與欄位限制說明（隔離合成資料）"
SERVICE_ENV_MARKERS = (
    "PIT",
    "FORMAL",
    "PROJECTION",
    "ARTIFACT",
    "EVIDENCE",
    "READINESS",
    "AUDIT",
    "MANIFEST",
    "WEEKLY_",
    "MONTHLY_REVENUE",
    "BANKTAIWAN",
    "RECOMMENDATION_LEARNING",
    "PAPER_",
)
_CHECKPOINT_LAST_WRITTEN: dict[str, float] = {}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="隔離 offscreen 真 MainWindow 全頁版面／捲動稽核 runner"
    )
    parser.add_argument(
        "--scale",
        action="append",
        dest="scales",
        help="Qt scale factor；可重複指定，預設為 1 與 1.5",
    )
    parser.add_argument(
        "--geometry",
        action="append",
        choices=tuple(GEOMETRIES),
        help="只稽核指定幾何；可重複指定，預設全部三種尺寸",
    )
    parser.add_argument(
        "--workspace",
        action="append",
        choices=EXPECTED_WORKSPACES,
        help="只稽核指定工作區；可重複指定，預設全部九個工作區",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path("output") / "qa" / "ui_layout_20260929" / "mainwindow_audit"),
        help="JSON、Markdown 與截圖輸出目錄（應位於 ignored QA output）",
    )
    parser.add_argument("--_child", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


@contextmanager
def _capture_qt_slot_exceptions() -> Iterator[list[dict[str, str]]]:
    """Record uncaught PySide slot errors instead of letting empty pages pass."""

    import traceback

    captured: list[dict[str, str]] = []
    original_hook = sys.excepthook

    def capture(exception_type: type[BaseException], value: BaseException, tb: Any) -> None:
        captured.append(
            {
                "message": f"{exception_type.__name__}: {value}",
                "traceback": "".join(traceback.format_exception(exception_type, value, tb)),
            }
        )

    sys.excepthook = capture
    try:
        yield captured
    finally:
        sys.excepthook = original_hook


def _enable_faulthandler_log(path: Path) -> TextIO:
    """Keep a dedicated fatal-error log open for the full child QA lifetime."""

    stack_log = path.open("a", encoding="utf-8")
    try:
        faulthandler.enable(file=stack_log, all_threads=True)
    except BaseException:
        stack_log.close()
        raise
    return stack_log


def _disable_and_close_faulthandler_log(stack_log: TextIO) -> None:
    """Disable native fatal handlers before their file descriptor is closed."""

    # If disable fails, deliberately leave the stream open so an enabled native
    # handler cannot write through a closed/reused file descriptor.
    faulthandler.disable()
    stack_log.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    geometries = tuple(args.geometry or GEOMETRIES)
    workspaces = tuple(args.workspace or EXPECTED_WORKSPACES)
    scales = tuple(args.scales or DEFAULT_SCALES)
    if args._child:
        scale = os.environ.get("QT_SCALE_FACTOR", "")
        stack_log = _enable_faulthandler_log(output_dir / "faulthandler.log")
        try:
            with _capture_qt_slot_exceptions() as qt_slot_exceptions:
                try:
                    evidence = _run_child(
                        scale=scale,
                        geometries=geometries,
                        workspaces=workspaces,
                        output_dir=output_dir,
                    )
                except BaseException as exc:  # noqa: BLE001 - runner must persist failures
                    evidence = {
                        "status": "failed",
                        "scale_factor_requested": scale,
                        "evidence_kind": "offscreen_real_mainwindow_geometry",
                        "errors": [
                            {
                                "severity": "fail",
                                "code": "runner_exception",
                                "message": f"{type(exc).__name__}: {exc}",
                            }
                        ],
                        "traceback": _format_traceback(exc),
                    }
            for slot_exception in qt_slot_exceptions:
                evidence.setdefault("errors", []).append(
                    {
                        "severity": "fail",
                        "code": "qt_slot_exception",
                        "message": slot_exception["message"],
                        "traceback": slot_exception["traceback"],
                    }
                )
            if qt_slot_exceptions:
                evidence["status"] = "failed"
        finally:
            _disable_and_close_faulthandler_log(stack_log)
        _write_evidence(output_dir, evidence, partial=False)
        return 0 if evidence.get("status") == "passed" else 1

    results: list[dict[str, Any]] = []
    script_path = Path(__file__).resolve()
    for scale in scales:
        _validate_scale(scale)
        scale_name = _scale_name(scale)
        scale_dir = output_dir / scale_name
        scale_dir.mkdir(parents=True, exist_ok=True)
        completed_children: list[dict[str, Any]] = []
        for geometry in geometries:
            child_dir = scale_dir / "geometry_processes" / geometry
            child_dir.mkdir(parents=True, exist_ok=True)
            env = _isolated_child_environment(os.environ.copy(), scale, child_dir)
            command = _geometry_child_command(
                script_path=script_path,
                output_dir=child_dir,
                geometry=geometry,
                workspaces=workspaces,
            )
            process_info: dict[str, Any]
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(project_root),
                    env=env,
                    text=True,
                    capture_output=True,
                    encoding="utf-8",
                    errors="backslashreplace",
                    timeout=900,
                    check=False,
                )
                process_info = {
                    "geometry": geometry,
                    "returncode": completed.returncode,
                    "stdout_tail": completed.stdout[-2500:],
                    "stderr_tail": completed.stderr[-2500:],
                    "output_dir": str(child_dir),
                }
                child_result = _read_geometry_child_evidence(
                    scale=scale,
                    geometry=geometry,
                    child_dir=child_dir,
                    returncode=completed.returncode,
                )
            except subprocess.TimeoutExpired as exc:
                process_info = {
                    "geometry": geometry,
                    "returncode": None,
                    "timeout_seconds": 900,
                    "stdout_tail": _decode_process_output(exc.stdout)[-2500:],
                    "stderr_tail": _decode_process_output(exc.stderr)[-2500:],
                    "output_dir": str(child_dir),
                }
                child_result = _timeout_result(scale, child_dir, exc)

            completed_children.append(
                {
                    "geometry": geometry,
                    "evidence": child_result,
                    "process": process_info,
                }
            )
            result = _combine_geometry_child_results(scale, completed_children)
            _write_evidence(scale_dir, result, partial=True)

        result = _combine_geometry_child_results(scale, completed_children)
        _write_evidence(scale_dir, result, partial=False)
        results.append(result)
        _write_summary(output_dir, results, complete=False)

    _write_summary(output_dir, results, complete=True)
    return 0 if all(result.get("status") == "passed" for result in results) else 1


def _validate_scale(value: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"scale 必須是正數：{value!r}") from exc
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"scale 必須是正數：{value!r}")
    return numeric


def _geometry_child_command(
    *,
    script_path: Path,
    output_dir: Path,
    geometry: str,
    workspaces: tuple[str, ...],
) -> list[str]:
    """Build one fresh Qt process command for exactly one window geometry."""

    if geometry not in GEOMETRIES:
        raise ValueError(f"未知視窗幾何：{geometry}")
    command = [
        sys.executable,
        str(script_path),
        "--_child",
        "--output-dir",
        str(output_dir),
        "--geometry",
        geometry,
    ]
    for workspace in workspaces:
        command.extend(("--workspace", workspace))
    return command


def _decode_process_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="backslashreplace")
    return value


def _read_geometry_child_evidence(
    *,
    scale: str,
    geometry: str,
    child_dir: Path,
    returncode: int,
) -> dict[str, Any]:
    evidence_path = child_dir / "evidence.json"
    partial_path = child_dir / "evidence.partial.json"
    source_path = evidence_path if evidence_path.exists() else partial_path
    if source_path.exists():
        child_result = json.loads(source_path.read_text(encoding="utf-8"))
    else:
        child_result = {
            "status": "failed",
            "scale_factor_requested": _validate_scale(scale),
            "geometry_runs": [],
            "errors": [
                {
                    "severity": "fail",
                    "code": "child_no_evidence",
                    "message": (
                        f"{geometry} child 沒有產生 JSON evidence；"
                        f"returncode={returncode}"
                    ),
                }
            ],
            "coverage_gaps": [],
            "screenshots": [],
        }

    errors = child_result.setdefault("errors", [])
    geometry_keys = [
        item.get("key")
        for item in child_result.get("geometry_runs", [])
        if isinstance(item, dict)
    ]
    if geometry_keys != [geometry]:
        errors.append(
            {
                "severity": "fail",
                "code": "geometry_child_receipt_mismatch",
                "message": (
                    f"{geometry} child receipt 必須且只能包含該幾何；"
                    f"實際為 {geometry_keys!r}"
                ),
            }
        )
    if returncode != 0 and not any(
        error.get("code") in {"child_process_exit_nonzero", "runner_timeout"}
        for error in errors
    ):
        errors.append(
            {
                "severity": "fail",
                "code": "child_process_exit_nonzero",
                "message": f"{geometry} child exit code {returncode}",
            }
        )
    if child_result.get("status") != "passed" and not errors:
        errors.append(
            {
                "severity": "fail",
                "code": "geometry_child_status_failed",
                "message": (
                    f"{geometry} child 狀態為 {child_result.get('status', 'missing')}，"
                    "未能提供 passed receipt"
                ),
            }
        )
    if (
        returncode != 0
        or errors
        or child_result.get("coverage_gaps")
        or child_result.get("status") != "passed"
    ):
        child_result["status"] = "failed"
    return child_result


def _combine_geometry_child_results(
    scale: str, children: list[dict[str, Any]]
) -> dict[str, Any]:
    """Combine independent per-geometry Qt receipts without dropping failures."""

    if not children:
        return {
            "status": "failed",
            "evidence_kind": "offscreen_real_mainwindow_geometry",
            "scale_factor_requested": _validate_scale(scale),
            "geometry_runs": [],
            "errors": [
                {
                    "severity": "fail",
                    "code": "geometry_child_missing",
                    "message": "沒有啟動任何獨立幾何 child process",
                }
            ],
            "coverage_gaps": [],
            "screenshots": [],
            "child_processes": [],
        }

    first = children[0]["evidence"]
    combined: dict[str, Any] = {
        key: first[key]
        for key in (
            "evidence_kind",
            "native_window_frame",
            "actual_maximum_geometry",
            "scale_factor_requested",
            "scale_factor_observed",
            "profile",
            "theme_font",
            "theme_cjk_glyph_available",
        )
        if key in first
    }
    combined.update(
        {
            "status": "running",
            "geometry_runs": [],
            "errors": [],
            "coverage_gaps": [],
            "screenshots": [],
            "startup_service_read_dispatches_suppressed": [],
            "isolated_paths_by_geometry": {},
            "isolated_file_inventory_by_geometry": {},
            "child_processes": [],
        }
    )
    for child in children:
        geometry = child["geometry"]
        result = child["evidence"]
        combined["geometry_runs"].extend(result.get("geometry_runs", []))
        combined["errors"].extend(result.get("errors", []))
        combined["coverage_gaps"].extend(result.get("coverage_gaps", []))
        combined["screenshots"].extend(result.get("screenshots", []))
        combined["startup_service_read_dispatches_suppressed"].extend(
            result.get("startup_service_read_dispatches_suppressed", [])
        )
        combined["isolated_paths_by_geometry"][geometry] = result.get(
            "isolated_paths", {}
        )
        combined["isolated_file_inventory_by_geometry"][geometry] = result.get(
            "isolated_file_inventory", []
        )
        combined["child_processes"].append(child["process"])
    combined["isolated_paths"] = combined["isolated_paths_by_geometry"].get(
        children[0]["geometry"], {}
    )
    combined["isolated_file_inventory"] = [
        {
            "geometry": geometry,
            "files": records,
        }
        for geometry, records in combined["isolated_file_inventory_by_geometry"].items()
    ]
    child_statuses_passed = all(
        child["evidence"].get("status") == "passed" for child in children
    )
    combined["status"] = (
        "failed"
        if combined["errors"] or combined["coverage_gaps"] or not child_statuses_passed
        else "passed"
    )
    return combined


def _scale_name(value: str) -> str:
    return f"scale_{value.replace('.', '_')}"


@contextmanager
def _suppress_mainwindow_constructor_data_reads() -> Iterator[list[str]]:
    """Keep the real shell while disabling constructors' eager service reads."""

    from ui_qt.views.portfolio_view import PortfolioView
    from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView

    original_workbench_refresh = UnifiedDecisionWorkbenchView.refresh_dashboard
    original_portfolio_refresh = PortfolioView.refresh_all
    suppressed: list[str] = []

    def pending_workbench(self: Any) -> None:
        self._display_pending_dashboard()

    def pending_portfolio(self: Any) -> None:
        return None

    UnifiedDecisionWorkbenchView.refresh_dashboard = pending_workbench
    PortfolioView.refresh_all = pending_portfolio
    suppressed.extend(
        (
            "UnifiedDecisionWorkbenchView.refresh_dashboard during MainWindow construction",
            "PortfolioView.refresh_all during MainWindow construction",
        )
    )
    try:
        yield suppressed
    finally:
        UnifiedDecisionWorkbenchView.refresh_dashboard = original_workbench_refresh
        PortfolioView.refresh_all = original_portfolio_refresh


def _isolated_child_environment(
    base: dict[str, str], scale: str, output_dir: Path
) -> dict[str, str]:
    env = dict(base)
    for name in tuple(env):
        upper = name.upper()
        if name.endswith("_PATH") or name.endswith("_ROOT") or any(
            marker in upper for marker in SERVICE_ENV_MARKERS
        ):
            env.pop(name, None)
    isolated = output_dir / "_isolated_app"
    for folder in ("data", "output", "config", "local_app_data", "tmp"):
        (isolated / folder).mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_SCALE_FACTOR": scale,
            "PYTHONIOENCODING": "utf-8",
            "DATA_ROOT": str(isolated / "data"),
            "OUTPUT_ROOT": str(isolated / "output"),
            "PROFILE": "test",
            "FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE": str(
                (isolated / "config" / "formal_runtime_binding_does_not_exist.json").resolve()
            ),
            "APPDATA": str(isolated / "config"),
            "LOCALAPPDATA": str(isolated / "local_app_data"),
            "XDG_CONFIG_HOME": str(isolated / "config"),
            "TEMP": str(isolated / "tmp"),
            "TMP": str(isolated / "tmp"),
        }
    )
    return env


def _run_child(
    *,
    scale: str,
    geometries: tuple[str, ...],
    workspaces: tuple[str, ...],
    output_dir: Path,
) -> dict[str, Any]:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    requested_scale = _validate_scale(scale)
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    os.environ["PYTHONIOENCODING"] = "utf-8"
    isolated_root = output_dir / "_isolated_app"
    for folder in ("data", "output", "config", "local_app_data", "tmp"):
        (isolated_root / folder).mkdir(parents=True, exist_ok=True)
    os.environ["DATA_ROOT"] = str(isolated_root / "data")
    os.environ["OUTPUT_ROOT"] = str(isolated_root / "output")
    os.environ["PROFILE"] = "test"
    os.environ["FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE"] = str(
        (isolated_root / "config" / "formal_runtime_binding_does_not_exist.json").resolve()
    )
    os.environ["APPDATA"] = str(isolated_root / "config")
    os.environ["LOCALAPPDATA"] = str(isolated_root / "local_app_data")
    os.environ["XDG_CONFIG_HOME"] = str(isolated_root / "config")
    os.environ["TEMP"] = str(isolated_root / "tmp")
    os.environ["TMP"] = str(isolated_root / "tmp")

    import pandas as pd
    from PySide6.QtCore import QModelIndex, Qt, QTimer
    from PySide6.QtGui import QFontMetrics, QGuiApplication
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QAbstractButton,
        QAbstractItemView,
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QGroupBox,
        QHeaderView,
        QLabel,
        QLineEdit,
        QListView,
        QListWidget,
        QMainWindow,
        QPlainTextEdit,
        QPushButton,
        QRadioButton,
        QScrollArea,
        QStackedWidget,
        QTableView,
        QTableWidget,
        QTabWidget,
        QTextBrowser,
        QTextEdit,
        QTreeView,
        QTreeWidget,
        QWidget,
    )
    from ui_qt.main import MainWindow, apply_app_theme
    from ui_qt.models.pandas_table_model import PandasTableModel

    qt_app = QApplication.instance()
    app = qt_app if isinstance(qt_app, QApplication) else QApplication(sys.argv)
    apply_app_theme(app)
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        raise AssertionError("offscreen Qt 沒有 primary screen")
    observed_scale = float(screen.devicePixelRatio())
    evidence: dict[str, Any] = {
        "status": "running",
        "evidence_kind": "offscreen_real_mainwindow_geometry",
        "native_window_frame": "not_measured_offscreen",
        "actual_maximum_geometry": "2293x912 logical client-size emulation",
        "scale_factor_requested": requested_scale,
        "scale_factor_observed": observed_scale,
        "profile": os.environ["PROFILE"],
        "isolated_paths": {
            "data_root": os.environ["DATA_ROOT"],
            "output_root": os.environ["OUTPUT_ROOT"],
            "personal_policy": str((isolated_root / "config" / "personal_use_policy.json").resolve()),
            "app_config": os.environ["APPDATA"],
            "temp": os.environ["TEMP"],
            "formal_runtime_binding": os.environ["FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE"],
            "formal_runtime_binding_exists": Path(
                os.environ["FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE"]
            ).exists(),
        },
        "startup_service_read_dispatches_suppressed": [],
        "geometry_runs": [],
        "errors": [],
        "coverage_gaps": [],
        "screenshots": [],
    }
    if not math.isclose(observed_scale, requested_scale, rel_tol=0, abs_tol=0.01):
        evidence["errors"].append(
            {
                "severity": "fail",
                "code": "scale_mismatch",
                "message": f"requested={requested_scale}, observed={observed_scale}",
            }
        )
    if not QFontMetrics(app.font()).inFont("推"):
        evidence["errors"].append(
            {
                "severity": "fail",
                "code": "cjk_font_missing",
                "message": "套用正式 theme 後字型不支援 CJK 驗證字元「推」",
            }
        )
    evidence["theme_font"] = app.font().family()
    evidence["theme_cjk_glyph_available"] = bool(QFontMetrics(app.font()).inFont("推"))

    for geometry_key in geometries:
        width, height, geometry_label = GEOMETRIES[geometry_key]
        geometry_dir = output_dir / "screenshots" / _scale_name(scale) / geometry_key
        geometry_dir.mkdir(parents=True, exist_ok=True)
        geometry_evidence: dict[str, Any] = {
            "key": geometry_key,
            "label": geometry_label,
            "requested_size_logical": {"width": width, "height": height},
            "measurement_mode": (
                "offscreen logical-size equivalent to observed Windows available geometry"
                if geometry_key == "actual_max"
                else "offscreen logical client geometry"
            ),
            "workspaces": [],
            "errors": [],
        }
        evidence["geometry_runs"].append(geometry_evidence)
        window: QMainWindow | None = None
        try:
            with _suppress_mainwindow_constructor_data_reads() as suppressed_startup_reads:
                window = MainWindow(
                    policy_config_path=str(
                        (isolated_root / "config" / "personal_use_policy.json").resolve()
                    )
                )
            evidence["startup_service_read_dispatches_suppressed"].append(
                {
                    "geometry": geometry_key,
                    "dispatches": suppressed_startup_reads,
                }
            )
            decision_desk = getattr(window, "decision_desk_view", None)
            if decision_desk is not None and hasattr(
                decision_desk, "_auto_refresh_pending"
            ):
                decision_desk._auto_refresh_pending = False
            _stop_periodic_ui_refresh_timers(window, evidence)
            _suppress_known_service_refresh_signals(window, evidence)
            window.show()
            window.resize(width, height)
            app.processEvents()
            QTest.qWait(12)
            app.processEvents()
            actual_size = window.size()
            geometry_evidence["observed_main_window_size_logical"] = {
                "width": int(actual_size.width()),
                "height": int(actual_size.height()),
            }
            geometry_evidence["frame_geometry_logical"] = {
                "x": int(window.frameGeometry().x()),
                "y": int(window.frameGeometry().y()),
                "width": int(window.frameGeometry().width()),
                "height": int(window.frameGeometry().height()),
            }
            nav = getattr(window, "left_navigation", None)
            workspace_stack = getattr(window, "workspace_stack", None)
            central = window.centralWidget()
            geometry_evidence["shell"] = _shell_metrics(window, nav, workspace_stack, central)
            if actual_size.width() != width or actual_size.height() != height:
                _add_error(
                    evidence,
                    geometry_evidence,
                    code="mainwindow_did_not_fit_requested_size",
                    message=(
                        f"請求 {width}x{height}，MainWindow 實際為 "
                        f"{actual_size.width()}x{actual_size.height()}"
                    ),
                    workspace=None,
                    page=None,
                    widget="MainWindow",
                )
            if nav is None or workspace_stack is None or central is None:
                _add_error(
                    evidence,
                    geometry_evidence,
                    code="real_shell_missing",
                    message="MainWindow 缺少左側導覽、workspace stack 或 centralWidget",
                    workspace=None,
                    page=None,
                    widget="MainWindow",
                )
            elif int(nav.width()) not in (184, 58):
                _add_error(
                    evidence,
                    geometry_evidence,
                    code="left_navigation_geometry_invalid",
                    message=f"真實左側導覽寬度不符預期：{nav.width()} logical px",
                    workspace=None,
                    page=None,
                    widget="left_navigation",
                )

            workspace_widgets = getattr(window, "workspace_widgets", {})
            missing_workspaces = [key for key in EXPECTED_WORKSPACES if key not in workspace_widgets]
            for missing in missing_workspaces:
                _add_error(
                    evidence,
                    geometry_evidence,
                    code="workspace_missing",
                    message=f"真實 MainWindow 未建立工作區：{missing}",
                    workspace=missing,
                    page=None,
                    widget="workspace_widgets",
                )

            for workspace_key in workspaces:
                workspace = workspace_widgets.get(workspace_key)
                if workspace is None:
                    continue
                if workspace_stack is not None:
                    workspace_stack.setCurrentWidget(workspace)
                if nav is not None:
                    nav.set_current_key(workspace_key)
                app.processEvents()
                QTest.qWait(4)
                app.processEvents()
                size_after_switch = window.size()
                if size_after_switch.width() != width or size_after_switch.height() != height:
                    _add_error(
                        evidence,
                        geometry_evidence,
                        code="workspace_switch_expanded_mainwindow",
                        message=(
                            f"切至 {workspace_key} 後窗口變成 "
                            f"{size_after_switch.width()}x{size_after_switch.height()}，"
                            f"原幾何為 {width}x{height}"
                        ),
                        workspace=workspace_key,
                        page=workspace_key,
                        widget="MainWindow",
                    )
                workspace_result: dict[str, Any] = {
                    "key": workspace_key,
                    "label": _workspace_label(window, workspace_key),
                    "widget_class": type(workspace).__name__,
                    "widget_object_name": workspace.objectName(),
                    "visible": bool(workspace.isVisible()),
                    "geometry_logical": _rect_metrics(workspace.geometry()),
                    "pages": [],
                    "scenarios": [],
                    "errors": [],
                    "coverage_gaps": [],
                    "screenshot": None,
                    "scrollbottom_screenshots": [],
                }
                geometry_evidence["workspaces"].append(workspace_result)
                _append_run_event(
                    output_dir,
                    "workspace_start",
                    geometry=geometry_key,
                    workspace=workspace_key,
                )
                if not workspace.isVisible():
                    _add_error(
                        evidence,
                        geometry_evidence,
                        code="workspace_not_visible",
                        message="切換後 workspace widget 仍未顯示",
                        workspace=workspace_key,
                        page=workspace_key,
                        widget=type(workspace).__name__,
                    )

                root_screenshot = geometry_dir / f"{workspace_key}_entry.png"
                if _capture_widget(window, root_screenshot):
                    workspace_result["screenshot"] = str(root_screenshot)
                    workspace_result["screenshot_kind"] = "initial_data_state_before_synthetic_fixture"
                    evidence["screenshots"].append(str(root_screenshot))
                else:
                    _add_error(
                        evidence,
                        geometry_evidence,
                        code="workspace_screenshot_failed",
                        message=f"無法儲存 MainWindow 截圖：{root_screenshot.name}",
                        workspace=workspace_key,
                        page=workspace_key,
                        widget="MainWindow",
                    )

                _audit_page_tree(
                    root_widget=workspace,
                    path=workspace_key,
                    workspace_key=workspace_key,
                    geometry_key=geometry_key,
                    geometry_dir=geometry_dir,
                    window=window,
                    app=app,
                    evidence=evidence,
                    geometry_evidence=geometry_evidence,
                    workspace_evidence=workspace_result,
                    capture_page_screenshots=geometry_key == "actual_max",
                )
                _append_run_event(
                    output_dir,
                    "workspace_tree_complete",
                    geometry=geometry_key,
                    workspace=workspace_key,
                    pages=len(workspace_result["pages"]),
                )
                _capture_workspace_scrollbottom(
                    workspace=workspace,
                    window=window,
                    app=app,
                    geometry_dir=geometry_dir,
                    workspace_key=workspace_key,
                    geometry_key=geometry_key,
                    evidence=evidence,
                    geometry_evidence=geometry_evidence,
                    workspace_evidence=workspace_result,
                )
                _run_workspace_scenarios(
                    workspace_key=workspace_key,
                    workspace=workspace,
                    window=window,
                    app=app,
                    geometry_key=geometry_key,
                    geometry_dir=geometry_dir,
                    evidence=evidence,
                    geometry_evidence=geometry_evidence,
                    workspace_result=workspace_result,
                    capture_page_screenshots=geometry_key == "actual_max",
                )
                _append_run_event(
                    output_dir,
                    "workspace_complete",
                    geometry=geometry_key,
                    workspace=workspace_key,
                    pages=len(workspace_result["pages"]),
                    scenarios=len(workspace_result["scenarios"]),
                )
                _checkpoint_evidence(output_dir, evidence, force=True)
        except BaseException as exc:  # noqa: BLE001 - persist every page-level failure
            _add_error(
                evidence,
                geometry_evidence,
                code="geometry_run_exception",
                message=f"{type(exc).__name__}: {exc}",
                workspace=None,
                page=None,
                widget="MainWindow",
            )
            geometry_evidence["traceback"] = _format_traceback(exc)
        finally:
            if window is not None:
                window.close()
                app.processEvents()
                window.deleteLater()
                app.processEvents()
            _checkpoint_evidence(output_dir, evidence, force=True)

    evidence["isolated_file_inventory"] = _isolated_file_inventory(isolated_root)
    evidence["status"] = "failed" if evidence["errors"] or evidence["coverage_gaps"] else "passed"
    return evidence


def _capture_scenario_focus_screenshot(
    *,
    spec: dict[str, Any],
    workspace: QWidget,
    window: QWidget,
    app: QApplication,
    geometry_key: str,
    geometry_dir: Path,
    evidence: dict[str, Any],
    geometry_evidence: dict[str, Any],
    workspace_key: str,
    scenario: dict[str, Any],
) -> None:
    """Scroll a named scenario target into view and capture its real window state."""
    target_name = spec.get("focus_target_object_name")
    area_attribute = spec.get("focus_scroll_area_attribute")
    if not target_name or not area_attribute or geometry_key not in {"default", "actual_max"}:
        return

    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QScrollArea, QWidget

    area = getattr(workspace, str(area_attribute), None)
    target = workspace.findChild(QWidget, str(target_name))
    if not isinstance(area, QScrollArea) or target is None or area.widget() is None:
        _add_error(
            evidence,
            geometry_evidence,
            code="scenario_focus_target_missing",
            message=(
                f"情境截圖找不到 scroll area {area_attribute!r} 或 target {target_name!r}"
            ),
            workspace=workspace_key,
            page=str(spec.get("key", "scenario")),
            widget=str(target_name),
        )
        return
    if target is not area.widget() and not area.widget().isAncestorOf(target):
        _add_error(
            evidence,
            geometry_evidence,
            code="scenario_focus_target_outside_scroll_area",
            message=f"情境截圖 target {target_name!r} 不在指定 scroll area 內容中",
            workspace=workspace_key,
            page=str(spec.get("key", "scenario")),
            widget=str(target_name),
        )
        return

    area.ensureWidgetVisible(target)
    app.processEvents()
    _wait_layout(area)
    target_origin = target.mapTo(area.viewport(), QPoint(0, 0))
    target_rect = target.rect().translated(target_origin)
    visible_intersection = target_rect.intersected(area.viewport().rect())
    screenshot_path = geometry_dir / f"{spec.get('focus_screenshot_slug') or _slug(str(target_name))}.png"
    captured = bool(visible_intersection.isValid() and _capture_widget(window, screenshot_path))
    scenario["focus_screenshot"] = {
        "path": str(screenshot_path) if captured else None,
        "kind": "scenario_target_scrolled_into_view",
        "target_object_name": str(target_name),
        "scroll_area_object_name": area.objectName(),
        "target_rect_in_viewport": _rect_metrics(target_rect),
        "visible_intersection": _rect_metrics(visible_intersection),
        "viewport_size_logical": {
            "width": int(area.viewport().width()),
            "height": int(area.viewport().height()),
        },
        "vertical_scroll_value": int(area.verticalScrollBar().value()),
        "vertical_scroll_maximum": int(area.verticalScrollBar().maximum()),
        "geometry_key": geometry_key,
    }
    if captured:
        evidence.setdefault("screenshots", []).append(str(screenshot_path))
    else:
        _add_error(
            evidence,
            geometry_evidence,
            code="scenario_focus_screenshot_failed",
            message=f"無法顯示或儲存情境 target 截圖：{screenshot_path.name}",
            workspace=workspace_key,
            page=str(spec.get("key", "scenario")),
            widget=str(target_name),
        )


def _run_workspace_scenarios(
    *,
    workspace_key: str,
    workspace: QWidget,
    window: QWidget,
    app: QApplication,
    geometry_key: str,
    geometry_dir: Path,
    evidence: dict[str, Any],
    geometry_evidence: dict[str, Any],
    workspace_result: dict[str, Any],
    capture_page_screenshots: bool,
) -> None:
    """Exercise explicitly-expanded UI states without invoking their services."""

    from PySide6.QtTest import QTest

    for spec in _workspace_scenario_specs(workspace_key, workspace, window):
        _append_run_event(
            geometry_dir.parents[2],
            "scenario_start",
            geometry=geometry_key,
            workspace=workspace_key,
            scenario=spec["key"],
        )
        scenario: dict[str, Any] = {
            "key": spec["key"],
            "label": spec["label"],
            "description": spec["description"],
            "pages": [],
            "navigators": [],
            "errors": [],
            "coverage_gaps": [],
        }
        workspace_result["scenarios"].append(scenario)
        if not callable(spec.get("apply")):
            gap = _finding(
                "coverage_gap",
                "ui_scenario_hook_unavailable",
                str(spec.get("missing_reason") or "純 UI scenario hook 不可用"),
                workspace_key,
                spec["key"],
                None,
            )
            scenario["coverage_gaps"].append(gap)
            evidence["coverage_gaps"].append(gap)
            geometry_evidence.setdefault("workspace_coverage_gaps", []).append(gap)
            continue
        original_size = window.size()
        try:
            spec["apply"]()
            app.processEvents()
            QTest.qWait(4)
            app.processEvents()
            _capture_scenario_focus_screenshot(
                spec=spec,
                workspace=workspace,
                window=window,
                app=app,
                geometry_key=geometry_key,
                geometry_dir=geometry_dir,
                evidence=evidence,
                geometry_evidence=geometry_evidence,
                workspace_key=workspace_key,
                scenario=scenario,
            )
            audit_root = spec.get("audit_root", workspace)
            audit_path = spec.get(
                "audit_path", f"{workspace_key}/scenario:{spec['key']}"
            )
            _audit_page_tree(
                root_widget=audit_root,
                path=audit_path,
                workspace_key=workspace_key,
                geometry_key=geometry_key,
                geometry_dir=geometry_dir,
                window=window,
                app=app,
                evidence=evidence,
                geometry_evidence=geometry_evidence,
                workspace_evidence=scenario,
                capture_page_screenshots=capture_page_screenshots,
            )
            scenario["main_window_size_logical"] = {
                "width": int(window.width()),
                "height": int(window.height()),
            }
            scenario["main_window_size_unchanged"] = window.size() == original_size
            if not scenario["main_window_size_unchanged"]:
                _add_error(
                    evidence,
                    geometry_evidence,
                    code="scenario_expanded_mainwindow",
                    message=(
                        f"{spec['key']} scenario 後主視窗尺寸從 "
                        f"{original_size.width()}x{original_size.height()} 變成 "
                        f"{window.width()}x{window.height()}"
                    ),
                    workspace=workspace_key,
                    page=spec["key"],
                    widget="MainWindow",
                )
        except BaseException as exc:  # noqa: BLE001 - retain scenario-specific failures
            error = _finding(
                "fail",
                "ui_scenario_exception",
                f"{type(exc).__name__}: {exc}",
                workspace_key,
                spec["key"],
                None,
            )
            scenario["errors"].append(error)
            evidence["errors"].append(error)
            geometry_evidence.setdefault("errors", []).append(error)
            scenario["traceback"] = _format_traceback(exc)
        finally:
            restore = spec.get("restore")
            if callable(restore):
                try:
                    restore()
                except BaseException as exc:  # noqa: BLE001 - note a failed reset explicitly
                    error = _finding(
                        "fail",
                        "ui_scenario_restore_failed",
                        f"{type(exc).__name__}: {exc}",
                        workspace_key,
                        spec["key"],
                        None,
                    )
                    scenario["errors"].append(error)
                    evidence["errors"].append(error)
                    geometry_evidence.setdefault("errors", []).append(error)
            app.processEvents()
            _checkpoint_evidence(geometry_dir.parents[2], evidence, force=True)
            _append_run_event(
                geometry_dir.parents[2],
                "scenario_complete",
                geometry=geometry_key,
                workspace=workspace_key,
                scenario=spec["key"],
                pages=len(scenario["pages"]),
            )


def _workspace_scenario_specs(
    workspace_key: str, workspace: QWidget, window: QWidget
) -> list[dict[str, Any]]:
    from PySide6.QtWidgets import QWidget

    if workspace_key == "workbench":
        from ui_qt.widgets.theme_widgets import CollapsibleSectionPanel

        panels = workspace.findChildren(CollapsibleSectionPanel)
        specs: list[dict[str, Any]] = []
        if not panels:
            specs.append(
                {
                    "key": "all_sections_expanded",
                    "label": "工作台所有折疊區展開",
                    "description": "展開每個 CollapsibleSectionPanel 以檢查全部說明和資料區。",
                    "missing_reason": "工作台沒有找到 CollapsibleSectionPanel。",
                }
            )
        else:
            old_states = [panel.is_collapsed() for panel in panels]
            specs.append(
                {
                    "key": "all_sections_expanded",
                    "label": "工作台所有折疊區展開",
                    "description": "純 UI 呼叫 CollapsibleSectionPanel.set_collapsed(False)，逐 tab 檢查展開內容。",
                    "apply": lambda: [panel.set_collapsed(False) for panel in panels],
                    "restore": lambda: [panel.set_collapsed(state) for panel, state in zip(panels, old_states)],
                    "panel_count": len(panels),
                }
            )

        console_view = getattr(workspace, "research_console_view", None)
        old_console = getattr(console_view, "_console", None)
        if console_view is None or not callable(getattr(console_view, "render_console", None)):
            specs.append(
                {
                    "key": "synthetic_research_console",
                    "label": "研究控制台合成內容",
                    "description": "以唯讀 ResearchConsoleDTO 量測動態表格與長欄位。",
                    "missing_reason": "WorkBench 未建立 ResearchConsoleView。",
                }
            )
        elif old_console is None:
            specs.append(
                {
                    "key": "synthetic_research_console",
                    "label": "研究控制台合成內容",
                    "description": "以唯讀 ResearchConsoleDTO 量測動態表格與長欄位。",
                    "missing_reason": "ResearchConsoleView 未保留可還原的 baseline DTO。",
                }
            )
        else:
            synthetic_console = _synthetic_research_console()
            workbench_tabs = getattr(workspace, "subtabs", None)
            old_workbench_tab = (
                int(workbench_tabs.currentIndex()) if workbench_tabs is not None else -1
            )

            def apply_console_fixture() -> None:
                if workbench_tabs is not None:
                    workbench_tabs.setCurrentWidget(console_view)
                console_view.render_console(synthetic_console)

            def restore_console_fixture() -> None:
                console_view.render_console(old_console)
                if workbench_tabs is not None and old_workbench_tab >= 0:
                    workbench_tabs.setCurrentIndex(old_workbench_tab)

            specs.append(
                {
                    "key": "synthetic_research_console",
                    "label": "研究控制台合成內容",
                    "description": "直接呼叫 render_console(合成 DTO)，不觸發 source service。",
                    "apply": apply_console_fixture,
                    "restore": restore_console_fixture,
                    "audit_root": console_view,
                    "audit_path": "workbench/scenario:synthetic_research_console",
                }
            )
        return specs

    if workspace_key == "market_explore":
        regimes = [
            page
            for page in workspace.findChildren(QWidget)
            if hasattr(page, "layer3_group") and hasattr(page, "_on_layer3_toggled")
        ]
        if not regimes:
            return [
                {
                    "key": "regime_layer3_expanded",
                    "label": "市場總覽 Layer 3 技術細節展開",
                    "description": "展開純 UI 技術細節 group。",
                    "missing_reason": "市場工作區未找到有 layer3_group 的 regime page。",
                }
            ]
        old_states = [regime.layer3_group.isChecked() for regime in regimes]
        return [
            {
                "key": "regime_layer3_expanded",
                "label": "市場總覽 Layer 3 技術細節展開",
                "description": "QGroupBox.setChecked(True) 只切換 layer 3 可見性。",
                "apply": lambda: [regime.layer3_group.setChecked(True) for regime in regimes],
                "restore": lambda: [regime.layer3_group.setChecked(state) for regime, state in zip(regimes, old_states)],
                "page_count": len(regimes),
            }
        ]

    if workspace_key == "recommendation":
        view = workspace
        toggle = getattr(view, "profile_details_toggle", None)
        update_mode_ui = getattr(view, "_update_mode_ui", None)
        if toggle is None or not callable(update_mode_ui):
            return [
                {
                    "key": "advanced_personal_calibration",
                    "label": "推薦分析進階個人校準內容",
                    "description": "切換既有進階模式並展開個人校準說明。",
                    "missing_reason": "Recommendation 缺少個人詳細說明或純 UI mode refresh hook。",
                }
            ]
        old_beginner_mode = bool(getattr(view, "is_beginner_mode", True))
        old_details = bool(toggle.isChecked())

        def apply_advanced_personal_calibration() -> None:
            view.is_beginner_mode = False
            update_mode_ui()
            toggle.setChecked(True)

        def restore_personal_calibration() -> None:
            toggle.setChecked(old_details)
            view.is_beginner_mode = old_beginner_mode
            update_mode_ui()

        return [
            {
                "key": "advanced_personal_calibration",
                "label": "推薦分析進階個人校準內容",
                "description": "只呼叫 _update_mode_ui 與 profile_details_toggle，展開原有個人模式說明。",
                "apply": apply_advanced_personal_calibration,
                "restore": restore_personal_calibration,
                "focus_scroll_area_attribute": "result_scroll",
                "focus_target_object_name": "personalModelAssessmentControls",
                "focus_screenshot_slug": "recommendation_personal_model_assessment",
            }
        ]

    if workspace_key == "watchlist":
        toggle = getattr(workspace, "_toggle_advanced_research", None)
        if not callable(toggle):
            return [
                {
                    "key": "advanced_research_expanded",
                    "label": "觀察清單進階研究區展開",
                    "description": "顯示原有進階研究區。",
                    "missing_reason": "Watchlist 缺少純 UI _toggle_advanced_research hook。",
                }
            ]
        old_visible = bool(getattr(workspace, "analysis_group", None) and workspace.analysis_group.isVisible())
        return [
            {
                "key": "advanced_research_expanded",
                "label": "觀察清單進階研究區展開",
                "description": "呼叫 _toggle_advanced_research(True)，只變更研究區顯示狀態。",
                "apply": lambda: toggle(True),
                "restore": lambda: toggle(old_visible),
            }
        ]

    if workspace_key == "portfolio":
        toggle = getattr(workspace, "_toggle_advanced_portfolio", None)
        if not callable(toggle):
            return [
                {
                    "key": "advanced_portfolio_expanded",
                    "label": "Portfolio 進階研究區展開",
                    "description": "顯示交易歷史、日誌、模擬持倉和壓力測試等既有區塊。",
                    "missing_reason": "Portfolio 缺少純 UI _toggle_advanced_portfolio hook。",
                }
            ]
        old_visible = bool(getattr(workspace, "_advanced_details_visible", False))
        return [
            {
                "key": "advanced_portfolio_expanded",
                "label": "Portfolio 進階研究區展開",
                "description": "呼叫 _toggle_advanced_portfolio(True)，只更新可見性和 splitter 排版。",
                "apply": lambda: toggle(True),
                "restore": lambda: toggle(old_visible),
            }
        ]

    if workspace_key == "backtest":
        combo = getattr(workspace, "research_lab_mode_combo", None)
        modes = (
            "single_stock",
            "batch_stock",
            "fixed_basket",
            "recommendation_replay",
            "strategy_research",
        )
        if combo is None:
            return [
                {
                    "key": "all_research_modes",
                    "label": "五種 Research Lab 模式",
                    "description": "逐一檢查各研究模式的左側設定和右側語意分頁。",
                    "missing_reason": "Backtest 沒有 research_lab_mode_combo。",
                }
            ]
        old_index = int(combo.currentIndex())
        specs: list[dict[str, Any]] = []
        for mode in modes:
            index = combo.findData(mode)
            if index < 0:
                specs.append(
                    {
                        "key": f"mode_{mode}",
                        "label": f"回測模式：{mode}",
                        "description": "切換到 Research Lab 對應模式。",
                        "missing_reason": f"Research Lab combo 未提供 {mode} 選項。",
                    }
                )
                continue

            def apply_mode(mode_index: int = index) -> None:
                # currentIndexChanged only updates control visibility, mode
                # labels and semantic result tabs; execution buttons are never invoked.
                combo.setCurrentIndex(mode_index)

            def restore_mode() -> None:
                combo.setCurrentIndex(old_index)

            specs.append(
                {
                    "key": f"mode_{mode}",
                    "label": f"回測模式：{mode}",
                    "description": "Research Lab combo 同步純 UI controls 與 ResultPanel semantic tabs；未執行回測。",
                    "apply": apply_mode,
                    "restore": restore_mode,
                }
            )

        result_panel = getattr(workspace, "result_panel", None)
        registry_widget = getattr(result_panel, "run_registry_compare_widget", None)
        if registry_widget is None and callable(
            getattr(result_panel, "add_registry_compare_tab", None)
        ):
            registry_widget = result_panel.add_registry_compare_tab()
        registry_scroll = (
            getattr(result_panel, "_result_tab_widgets", {}).get("registry")
            if result_panel is not None
            else None
        )
        if registry_widget is None or registry_scroll is None:
            specs.append(
                {
                    "key": "research_registry_compare_fixture",
                    "label": "Research Run Compare 合成清單",
                    "description": "以隔離 metadata DTO 呈現比較清單，檢查五列與捲動。",
                    "missing_reason": "Backtest 未建立 Research Run Compare 的 registry tab。",
                }
            )
        else:
            synthetic_runs = _synthetic_research_runs()
            old_mode_index = int(combo.currentIndex()) if combo is not None else -1
            old_result_index = int(workspace.result_tabs.currentIndex())
            old_run_state = {
                "all_runs": list(registry_widget._all_runs),
                "filtered_runs": list(registry_widget._filtered_runs),
                "selected_run_ids": list(registry_widget._selected_run_ids),
                "current_page": int(registry_widget.current_page),
                "loaded_once": bool(registry_widget._loaded_once),
                "request_id": int(registry_widget._request_id),
                "instance_refresh": registry_widget.__dict__.get("refresh_runs"),
                "had_instance_refresh": "refresh_runs" in registry_widget.__dict__,
            }
            research_index = combo.findData("strategy_research") if combo is not None else -1

            def refresh_registry_fixture() -> None:
                registry_widget.apply_run_list_response(
                    registry_widget.begin_run_list_request(), synthetic_runs
                )

            def apply_registry_fixture() -> None:
                # Instance override prevents showEvent from calling the real run service.
                registry_widget.refresh_runs = refresh_registry_fixture
                if combo is not None and research_index >= 0:
                    combo.setCurrentIndex(research_index)
                workspace.result_panel.set_research_mode("strategy_research")
                workspace.result_panel.focus_result_tab("registry")
                refresh_registry_fixture()

            def restore_registry_fixture() -> None:
                if old_run_state["had_instance_refresh"]:
                    registry_widget.refresh_runs = old_run_state["instance_refresh"]
                else:
                    registry_widget.__dict__.pop("refresh_runs", None)
                registry_widget._all_runs = old_run_state["all_runs"]
                registry_widget._filtered_runs = old_run_state["filtered_runs"]
                registry_widget._selected_run_ids = old_run_state["selected_run_ids"]
                registry_widget.current_page = old_run_state["current_page"]
                registry_widget._request_id = old_run_state["request_id"]
                registry_widget._loaded_once = old_run_state["loaded_once"]
                registry_widget._render_run_list()
                if combo is not None and old_mode_index >= 0:
                    combo.setCurrentIndex(old_mode_index)
                old_mode = str(combo.currentData() or "single_stock") if combo is not None else "single_stock"
                workspace.result_panel.set_research_mode(old_mode)
                if 0 <= old_result_index < workspace.result_tabs.count():
                    workspace.result_tabs.setCurrentIndex(old_result_index)

            specs.append(
                {
                    "key": "research_registry_compare_fixture",
                    "label": "Research Run Compare 合成清單",
                    "description": "以 12 筆隔離 ResearchRunMetadataDTO 填入既有清單；刷新 hook 覆寫為純 UI fixture，不呼叫 service。",
                    "apply": apply_registry_fixture,
                    "restore": restore_registry_fixture,
                    "audit_root": registry_scroll,
                    "audit_path": "backtest/scenario:research_registry_compare_fixture",
                }
            )
        return specs

    if workspace_key == "stock_research":
        stock_workspace = getattr(window, "stock_research_workspace", None)
        report_view = getattr(stock_workspace, "report_view", None)
        if report_view is None or not callable(getattr(report_view, "_render_report", None)):
            return [
                {
                    "key": "synthetic_complete_report",
                    "label": "完整合成個股研究報告",
                    "description": "使用 read-only report DTO render 動態分頁及表格。",
                    "missing_reason": "StockResearch report view 不可用，動態 report tables 未驗。",
                }
            ]
        report = _synthetic_stock_research_report()

        def apply_report_fixture() -> None:
            report_view._render_report(report)
            report_view.summary_detail_toggle.setChecked(True)
            report_view.summary_source_toggle.setChecked(True)

        return [
            {
                "key": "synthetic_complete_report",
                "label": "完整合成個股研究報告",
                "description": "以 typed DTO 呼叫 report_view._render_report，未呼叫 service/read/update。",
                "apply": apply_report_fixture,
                "restore": lambda: report_view._clear_loaded_report(),
            }
        ]

    return []


def _synthetic_research_console() -> Any:
    from app_module.research_console_dtos import (
        ResearchArtifactRowDTO,
        ResearchConsoleBoundaryDTO,
        ResearchConsoleDTO,
        ResearchGateCardDTO,
        ResearchPipelineRowDTO,
        ResearchSourceRowDTO,
    )

    pipeline = tuple(
        ResearchPipelineRowDTO(
            component_id=f"qa-component-{row:02d}",
            label=f"合成研究管線 {row:02d}｜{LONG_CELL_TEXT}",
            identity=f"fixture:projection-{row:02d}",
            status="research_only_degraded",
            cutoff="2026-09-28",
            feature_interval="2026-09-01..2026-09-28",
            label_maturity="2026-09-28",
            row_count=80 + row,
            eligible_count=60 + row,
            feature_count=24 + row,
            artifact_path=f"qa-only/projection-{row:02d}.json",
            artifact_hash=f"sha256:qa-fixture-{row:02d}",
            blockers=(LONG_CELL_TEXT,),
        )
        for row in range(1, 9)
    )
    gates = tuple(
        ResearchGateCardDTO(
            gate_id=f"QA-EV{row:02d}",
            label=f"合成檢查項目 {row:02d}",
            status="missing" if row % 2 else "provisional",
            detail=LONG_CELL_TEXT,
            artifact_citation=f"qa-only/evidence-{row:02d}.json｜{LONG_CELL_TEXT}",
        )
        for row in range(1, 9)
    )
    sources = tuple(
        ResearchSourceRowDTO(
            source_id=f"qa.source.{row:02d}",
            label=f"合成來源 {row:02d}｜{LONG_CELL_TEXT}",
            lane="p0" if row % 2 else "broker",
            status="candidate" if row % 2 else "degraded",
            allowed_use=f"Research only｜{LONG_CELL_TEXT}",
            observed_rows=100 + row,
            revision=f"fixture-r{row:02d}",
            owner="QA layout runner",
            degraded_reason=LONG_CELL_TEXT,
        )
        for row in range(1, 9)
    )
    artifacts = tuple(
        ResearchArtifactRowDTO(
            artifact_type=f"qa_projection_{row:02d}",
            artifact_id=f"fixture:artifact-{row:02d}",
            status="development_only",
            citation=LONG_CELL_TEXT,
        )
        for row in range(1, 9)
    )
    return ResearchConsoleDTO(
        overall_status="degraded",
        source_reference="fixture:qa-layout-research-console.v1",
        boundary=ResearchConsoleBoundaryDTO(),
        pipeline=pipeline,
        gates=gates,
        sources=sources,
        artifacts=artifacts,
        frozen_metrics={"sample_count": 128, "coverage_bp": 8500},
        blockers=(LONG_CELL_TEXT,),
    )


def _synthetic_research_runs() -> list[Any]:
    from app_module.research_run_dtos import ResearchRunMetadataDTO

    return [
        ResearchRunMetadataDTO(
            run_id=f"qa-layout-run-{row:03d}",
            run_name=f"版面合成研究 run {row:03d}｜{LONG_CELL_TEXT}",
            run_type="single_backtest",
            strategy_id=f"qa_strategy_{row:03d}",
            strategy_version="qa-only-v1",
            parameter_contract_version="qa-layout.v1",
            universe=["QA0001", "QA0002"],
            start_date="2026-09-01",
            end_date="2026-09-28",
            data_cutoff_date="2026-09-28",
            data_fingerprint=f"sha256:qa-fixture-{row:03d}",
            fingerprint_algorithm="qa-only",
            capital_cents=10_000_000,
            fee_bp_x100=1425,
            slippage_bp_x100=500,
            execution_price="next_open",
            sizing_mode="fixed_amount",
            metrics={"sharpe_ratio": f"{row}.25", "fixture_note": LONG_CELL_TEXT},
            regime_breakdown={},
            benchmark_results={},
            payload_hash=f"sha256:qa-layout-run-{row:03d}",
            created_at=f"2026-09-{min(row, 28):02d}T12:00:00",
        )
        for row in range(1, 13)
    ]


def _synthetic_stock_research_report() -> Any:
    from dataclasses import dataclass
    from decimal import Decimal

    from app_module.stock_research_report_dtos import (
        StockEvidenceEventDTO,
        StockFlowObservationDTO,
        StockFundamentalObservationDTO,
        StockMetricDTO,
        StockPositionSnapshotDTO,
        StockPricePointDTO,
        StockReportSourceDTO,
        StockResearchReportDTO,
        StockTechnicalSnapshotDTO,
    )

    @dataclass(frozen=True)
    class LayoutPositionSnapshotDTO(StockPositionSnapshotDTO):
        """Typed fixture extension supplies report identity to shared presentation."""

        stock_code: str = "QA0001"
        stock_name: str = "版面合成標的"

    days = [f"2026-09-{day:02d}" for day in range(20, 29)]
    sources = tuple(
        StockReportSourceDTO(
            source_id=f"qa.fixture.{row}",
            source_label=f"版面合成來源 {row}",
            status="available",
            quality="observed",
            data_as_of=days[-1],
            available_at=f"{days[-1]}T18:00:00",
            freshness="fresh",
            version="qa-only",
            row_count=8,
            limitations=(LONG_CELL_TEXT,),
            frequency="daily",
            expected_period=days[-1],
            freshness_reason=LONG_CELL_TEXT,
        )
        for row in range(1, 6)
    )
    prices = tuple(
        StockPricePointDTO(
            data_date=day,
            open_price=Decimal("99") + Decimal(row),
            high_price=Decimal("103") + Decimal(row),
            low_price=Decimal("98") + Decimal(row),
            close_price=Decimal("101") + Decimal(row),
            volume=1_000_000 + row * 1_000,
            turnover=Decimal("101000000"),
            change=Decimal("1.25"),
            available_at=f"{day}T18:00:00",
            source_id="qa.fixture.price",
        )
        for row, day in enumerate(days)
    )
    metrics = tuple(
        StockMetricDTO(
            key=f"indicator_{row}",
            label=f"合成技術指標 {row}",
            value=Decimal(row * 10),
            unit="pt",
            data_as_of=days[-1],
            available_at=f"{days[-1]}T18:00:00",
            source_id="qa.fixture.technical",
        )
        for row in range(1, 7)
    )
    fundamentals = tuple(
        StockFundamentalObservationDTO(
            kind="monthly_revenue",
            label=f"合成月營收項目 {row}",
            period=f"2026-{row:02d}",
            as_of_date=days[-1],
            announced_date=days[-1],
            available_at=f"{days[-1]}T19:00:00",
            value=Decimal(1000 + row),
            unit="萬元",
            source_id="qa.fixture.fundamental",
            source_version="qa-only",
        )
        for row in range(1, 9)
    )
    flows = tuple(
        StockFlowObservationDTO(
            data_date=days[row % len(days)],
            branch_name=f"版面合成分點 {row:02d}",
            buy_shares=10_000 + row,
            sell_shares=8_000 + row,
            net_shares=2_000,
            net_amount_thousand=Decimal(300 + row),
            trade_type="qa-fixture",
            source_id="qa.fixture.flow",
        )
        for row in range(1, 9)
    )
    events = tuple(
        StockEvidenceEventDTO(
            event_id=f"qa-event-{row:02d}",
            event_date=days[row % len(days)],
            decision_date=days[row % len(days)],
            event_type="qa_layout_fixture",
            event_family="qa",
            source_type="synthetic_layout_only",
            source_id="qa.fixture.event",
            data_quality="observed",
            reasons=(LONG_CELL_TEXT,),
            warnings=(LONG_CELL_TEXT,),
            score_bp=row * 100,
        )
        for row in range(1, 9)
    )
    return StockResearchReportDTO(
        stock_code="QA0001",
        stock_name="版面合成標的",
        market="合成市場",
        industry="版面測試",
        as_of=days[-1],
        generated_at=f"{days[-1]}T20:00:00",
        sources=sources,
        attention_reasons=(LONG_CELL_TEXT,),
        key_risks=(LONG_CELL_TEXT,),
        limitations=(LONG_CELL_TEXT, "所有資料均為隔離合成資料。"),
        price_points=prices,
        technical=StockTechnicalSnapshotDTO(
            data_date=days[-1], indicators=metrics, source_id="qa.fixture.technical"
        ),
        fundamentals=fundamentals,
        flows=flows,
        institutional=metrics,
        credit=metrics,
        shareholding=metrics,
        events=events,
        position=LayoutPositionSnapshotDTO(
            is_holding=True,
            quantity=Decimal("10"),
            average_cost=Decimal("100"),
            invested_amount=Decimal("1000"),
            current_price=Decimal("101"),
            unrealized_pnl=Decimal("10"),
            unrealized_pnl_pct=Decimal("0.01"),
            exposure_bp=100,
            source_type="qa_fixture",
            source_id="qa.fixture.position",
            health_label="版面測試",
            health_reasons=(LONG_CELL_TEXT,),
            limitations=(LONG_CELL_TEXT,),
            stock_code="QA0001",
            stock_name="版面合成標的",
        ),
    )


def _stop_periodic_ui_refresh_timers(window: QWidget, evidence: dict[str, Any]) -> None:
    from PySide6.QtCore import QTimer

    stopped: list[dict[str, Any]] = []
    for timer in window.findChildren(QTimer):
        interval = int(timer.interval())
        name = timer.objectName().lower()
        if not timer.isSingleShot() and interval > 0 and any(
            marker in name for marker in ("refresh", "runtime", "poll", "status")
        ):
            timer.stop()
            stopped.append({"object_name": timer.objectName(), "interval_ms": interval})
    evidence["periodic_ui_timers_stopped"] = stopped


def _suppress_known_service_refresh_signals(window: QWidget, evidence: dict[str, Any]) -> None:
    suppressed: list[str] = []
    market_tabs = getattr(window, "market_tabs", None)
    market_callback = getattr(window, "_on_market_tab_changed", None)
    if market_tabs is not None and callable(market_callback):
        try:
            market_tabs.currentChanged.disconnect(market_callback)
            suppressed.append("market_tabs.currentChanged -> load_data_if_needed")
        except (RuntimeError, TypeError):
            pass
    backtest = getattr(window, "backtest_view", None)
    result_tabs = getattr(backtest, "result_tabs", None)
    result_callback = getattr(backtest, "_on_result_tab_changed", None)
    if result_tabs is not None and callable(result_callback):
        try:
            result_tabs.currentChanged.disconnect(result_callback)
            suppressed.append("backtest.result_tabs.currentChanged -> history/chart refresh")
        except (RuntimeError, TypeError):
            pass
    update_view = getattr(window, "update_view", None)
    update_nav = getattr(update_view, "nav_list", None)
    if update_nav is not None:
        suppressed.append("update_view.nav_list.currentRowChanged -> refresh/execute update")
    evidence["service_refresh_signal_suppression"] = suppressed


def _shell_metrics(
    window: QWidget, nav: QWidget | None, workspace_stack: QWidget | None, central: QWidget | None
) -> dict[str, Any]:
    central_rect = central.rect() if central is not None else None
    nav_rect = nav.geometry() if nav is not None else None
    stack_rect = workspace_stack.geometry() if workspace_stack is not None else None
    result: dict[str, Any] = {
        "central_size_logical": (
            {"width": int(central.width()), "height": int(central.height())}
            if central is not None
            else None
        ),
        "left_navigation": _rect_metrics(nav_rect) if nav_rect is not None else None,
        "workspace_stack": _rect_metrics(stack_rect) if stack_rect is not None else None,
        "navigation_fits_central": False,
        "workspace_fits_central": False,
    }
    if central_rect is not None and nav_rect is not None:
        result["navigation_fits_central"] = bool(
            nav_rect.x() >= central_rect.x()
            and nav_rect.y() >= central_rect.y()
            and nav_rect.right() <= central_rect.right()
            and nav_rect.bottom() <= central_rect.bottom()
        )
    if central_rect is not None and stack_rect is not None:
        result["workspace_fits_central"] = bool(
            stack_rect.x() >= central_rect.x()
            and stack_rect.y() >= central_rect.y()
            and stack_rect.right() <= central_rect.right()
            and stack_rect.bottom() <= central_rect.bottom()
            and stack_rect.width() > 0
            and stack_rect.height() > 0
        )
    return result


def _audit_page_tree(
    *,
    root_widget: QWidget,
    path: str,
    workspace_key: str,
    geometry_key: str,
    geometry_dir: Path,
    window: QWidget,
    app: QApplication,
    evidence: dict[str, Any],
    geometry_evidence: dict[str, Any],
    workspace_evidence: dict[str, Any],
    capture_page_screenshots: bool,
) -> None:
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QStackedWidget, QTabWidget

    visited_pages: set[int] = set()
    visited_navigators: set[int] = set()

    def audit_page(page_widget: QWidget, page_path: str) -> None:
        identity = id(page_widget)
        if identity in visited_pages:
            return
        visited_pages.add(identity)
        run_output_dir = geometry_dir.parents[2]
        _append_run_event(
            run_output_dir,
            "page_start",
            geometry=geometry_key,
            workspace=workspace_key,
            page=page_path,
            widget=type(page_widget).__name__,
        )
        app.processEvents()
        QTest.qWait(3)
        app.processEvents()
        page_entry: dict[str, Any] = {
            "path": page_path,
            "widget_class": type(page_widget).__name__,
            "widget_object_name": page_widget.objectName(),
            "visible": bool(page_widget.isVisible()),
            "geometry_logical": _rect_metrics(page_widget.geometry()),
            "tables_and_lists": [],
            "scroll_areas": [],
            "text_controls": [],
            "screenshot": None,
            "errors": [],
            "coverage_gaps": [],
        }
        workspace_evidence["pages"].append(page_entry)
        if not page_widget.isVisible():
            gap = _finding(
                "coverage_gap",
                "subpage_not_visible",
                "子頁切換後 widget 仍未成為可見頁，geometry 無法視為已驗",
                workspace_key,
                page_path,
                type(page_widget).__name__,
            )
            page_entry["coverage_gaps"].append(gap)
            workspace_evidence["coverage_gaps"].append(gap)
            evidence["coverage_gaps"].append(gap)

        _audit_page_item_views(
            page_widget,
            page_path,
            workspace_key,
            geometry_key,
            page_entry,
            evidence,
            geometry_evidence,
            window=window,
            geometry_dir=geometry_dir,
            capture_fixture_screenshot=(geometry_key in {"default", "actual_max"}),
        )
        _audit_page_scroll_areas(
            page_widget,
            page_path,
            workspace_key,
            page_entry,
            evidence,
            geometry_evidence,
            app,
        )
        _audit_page_text_controls(
            page_widget,
            page_path,
            workspace_key,
            page_entry,
            evidence,
            geometry_evidence,
        )
        if capture_page_screenshots:
            screenshot_path = geometry_dir / f"page_{_slug(page_path)}.png"
            if _capture_widget(window, screenshot_path):
                page_entry["screenshot"] = str(screenshot_path)
                page_entry["screenshot_kind"] = "page_state_after_fixture_models_restored"
                evidence["screenshots"].append(str(screenshot_path))
        _checkpoint_evidence(geometry_dir.parents[2], evidence)
        _append_run_event(
            run_output_dir,
            "page_complete",
            geometry=geometry_key,
            workspace=workspace_key,
            page=page_path,
            tables_and_lists=len(page_entry["tables_and_lists"]),
            scroll_areas=len(page_entry["scroll_areas"]),
        )

        for navigator in _visible_navigators(page_widget):
            if id(navigator) in visited_navigators:
                continue
            visited_navigators.add(id(navigator))
            _audit_navigator(
                navigator=navigator,
                parent_path=page_path,
                workspace_key=workspace_key,
                geometry_key=geometry_key,
                geometry_dir=geometry_dir,
                window=window,
                app=app,
                evidence=evidence,
                geometry_evidence=geometry_evidence,
                workspace_evidence=workspace_evidence,
                audit_page=audit_page,
            )

    if isinstance(root_widget, (QTabWidget, QStackedWidget)) and not _is_internal_tab_stack(root_widget):
        _audit_navigator(
            navigator=root_widget,
            parent_path=path,
            workspace_key=workspace_key,
            geometry_key=geometry_key,
            geometry_dir=geometry_dir,
            window=window,
            app=app,
            evidence=evidence,
            geometry_evidence=geometry_evidence,
            workspace_evidence=workspace_evidence,
            audit_page=audit_page,
        )
    else:
        audit_page(root_widget, path)


def _audit_navigator(
    *,
    navigator: QWidget,
    parent_path: str,
    workspace_key: str,
    geometry_key: str,
    geometry_dir: Path,
    window: QWidget,
    app: QApplication,
    evidence: dict[str, Any],
    geometry_evidence: dict[str, Any],
    workspace_evidence: dict[str, Any],
    audit_page: Any,
) -> None:
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QStackedWidget, QTabWidget

    if isinstance(navigator, QTabWidget):
        count = navigator.count()
        nav_kind = "tabs"
        nav_name = navigator.objectName() or type(navigator).__name__
    elif isinstance(navigator, QStackedWidget):
        count = navigator.count()
        nav_kind = "stack"
        nav_name = navigator.objectName() or type(navigator).__name__
    else:
        return
    index = next(
        (
            i
            for i in range(count)
            if navigator.widget(i) is not None and navigator.widget(i).isVisible()
        ),
        navigator.currentIndex(),
    )
    inventory = {
        "kind": nav_kind,
        "object_name": nav_name,
        "page_count": count,
        "pages": [],
    }
    workspace_evidence.setdefault("navigators", []).append(inventory)
    original_index = navigator.currentIndex()
    for page_index in range(count):
        previous_blocked = navigator.blockSignals(True) if _is_service_navigator(navigator, window) else None
        navigator.setCurrentIndex(page_index)
        if previous_blocked is not None:
            navigator.blockSignals(previous_blocked)
        app.processEvents()
        QTest.qWait(3)
        app.processEvents()
        _sync_update_navigation(navigator, page_index, window)
        page_widget = navigator.widget(page_index)
        if page_widget is None:
            label = f"{nav_name}[{page_index}]"
            page_path = f"{parent_path}/{label}"
            gap = _finding(
                "coverage_gap",
                "navigator_page_missing",
                "navigator 回傳空白 page widget",
                workspace_key,
                page_path,
                nav_name,
            )
            inventory["pages"].append({"index": page_index, "label": label, "path": page_path})
            workspace_evidence["coverage_gaps"].append(gap)
            evidence["coverage_gaps"].append(gap)
            continue
        label = _navigator_page_label(navigator, page_index, page_widget)
        page_path = f"{parent_path}/{label}"
        inventory["pages"].append(
            {
                "index": page_index,
                "label": label,
                "widget_class": type(page_widget).__name__,
                "widget_object_name": page_widget.objectName(),
                "path": page_path,
                "visible": bool(page_widget.isVisible()),
            }
        )
        audit_page(page_widget, page_path)
    if original_index >= 0 and original_index < count:
        previous_blocked = navigator.blockSignals(True) if _is_service_navigator(navigator, window) else None
        navigator.setCurrentIndex(original_index)
        if previous_blocked is not None:
            navigator.blockSignals(previous_blocked)
        _sync_update_navigation(navigator, original_index, window)
        app.processEvents()


def _visible_navigators(container: QWidget) -> list[QWidget]:
    from PySide6.QtWidgets import QStackedWidget, QTabWidget, QWidget

    result: list[QWidget] = []
    for candidate in container.findChildren(QWidget):
        if not candidate.isVisible() or candidate.isWindow():
            continue
        if not isinstance(candidate, (QTabWidget, QStackedWidget)):
            continue
        if _is_internal_tab_stack(candidate):
            continue
        result.append(candidate)
    return result


def _is_internal_tab_stack(widget: QWidget) -> bool:
    from PySide6.QtWidgets import QStackedWidget, QTabWidget

    return isinstance(widget, QStackedWidget) and isinstance(widget.parentWidget(), QTabWidget)


def _is_service_navigator(navigator: QWidget, window: QWidget) -> bool:
    if navigator is getattr(window, "market_tabs", None):
        return True
    backtest = getattr(window, "backtest_view", None)
    return navigator is getattr(backtest, "result_tabs", None)


def _sync_update_navigation(navigator: QWidget, index: int, window: QWidget) -> None:
    update_view = getattr(window, "update_view", None)
    content_stack = getattr(update_view, "content_stack", None)
    nav_list = getattr(update_view, "nav_list", None)
    if navigator is not content_stack or nav_list is None:
        return
    was_blocked = nav_list.blockSignals(True)
    nav_list.setCurrentRow(index)
    nav_list.blockSignals(was_blocked)


def _navigator_page_label(navigator: QWidget, index: int, page: QWidget) -> str:
    from PySide6.QtWidgets import QTabWidget

    if isinstance(navigator, QTabWidget):
        text = navigator.tabText(index).strip()
        if text:
            return text
    return page.objectName() or f"頁面 {index + 1}"


def _audit_page_item_views(
    page: QWidget,
    page_path: str,
    workspace_key: str,
    geometry_key: str,
    page_entry: dict[str, Any],
    evidence: dict[str, Any],
    geometry_evidence: dict[str, Any],
    *,
    window: QWidget,
    geometry_dir: Path,
    capture_fixture_screenshot: bool,
) -> None:
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QModelIndex, Qt
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QHeaderView,
        QListWidget,
        QTableView,
        QTableWidget,
        QTreeView,
        QTreeWidget,
        QWidget,
    )

    candidates = []
    if isinstance(page, QAbstractItemView):
        candidates.append(page)
    candidates.extend(page.findChildren(QAbstractItemView))
    seen: set[int] = set()
    for view in candidates:
        if id(view) in seen or isinstance(view, QHeaderView) or not view.isVisible():
            continue
        seen.add(id(view))
        model = view.model()
        baseline_rows = _model_count(model, "rowCount")
        baseline_columns = _model_count(model, "columnCount")
        entry: dict[str, Any] = {
            "object_name": view.objectName(),
            "class": type(view).__name__,
            "geometry_logical": _rect_metrics(view.geometry()),
            "viewport_size_logical": {
                "width": int(view.viewport().width()),
                "height": int(view.viewport().height()),
            },
            "minimum_height": int(view.minimumHeight()),
            "actual_height": int(view.height()),
            "visible_rows_helper": _visible_rows_helper_metrics(view),
            "first_five_rows": _item_view_rows_metrics(view, baseline_rows),
            "baseline_model": {
                "class": type(model).__name__ if model is not None else None,
                "rows": baseline_rows,
                "columns": baseline_columns,
                "empty": baseline_rows == 0,
                "horizontal_scroll_policy": _scroll_policy_name(view.horizontalScrollBarPolicy()),
                "horizontal_scroll_maximum": int(view.horizontalScrollBar().maximum()),
                "long_text_cells": [],
            },
            "fixture_stress": None,
            "supported": True,
        }
        page_entry["tables_and_lists"].append(entry)
        _inspect_baseline_long_cells(view, entry, evidence, geometry_evidence, workspace_key, page_path)

        if _is_update_navigation_list(view, page):
            entry["fixture_stress"] = {
                "skipped": True,
                "reason": "這是 Update 工作區的功能導航清單；替換其 item model 會改變子頁路由，因此保留原始導航項目並量測實際清單。",
                "existing_row_count": baseline_rows,
            }
            _check_native_list_rows(
                view,
                entry,
                evidence,
                geometry_evidence,
                workspace_key,
                page_path,
            )
            continue

        try:
            with _synthetic_view_data(view, rows=SYNTHETIC_ROW_COUNT) as fixture_info:
                _wait_layout(view)
                QTest.qWait(3)
                _wait_layout(view)
                fixture_model = view.model()
                stress_rows = _model_count(fixture_model, "rowCount")
                stress_columns = _model_count(fixture_model, "columnCount")
                fifth_index = fixture_model.index(4, 0) if stress_rows >= 5 else QModelIndex()
                view.verticalScrollBar().setValue(0)
                _wait_layout(view)
                fifth_rect = view.visualRect(fifth_index) if fifth_index.isValid() else None
                fifth_visible = bool(
                    fifth_rect is not None
                    and fifth_rect.isValid()
                    and fifth_rect.top() >= 0
                    and fifth_rect.bottom() < view.viewport().height()
                )
                if view.viewport().width() <= 0 or view.viewport().height() <= 0:
                    _add_error(
                        evidence,
                        geometry_evidence,
                        code="item_view_empty_viewport",
                        message="資料表／清單 viewport 沒有可用尺寸",
                        workspace=workspace_key,
                        page=page_path,
                        widget=type(view).__name__,
                    )
                if stress_rows < 8:
                    _add_error(
                        evidence,
                        geometry_evidence,
                        code="synthetic_item_count_too_small",
                        message=f"合成 fixture 僅有 {stress_rows} rows，少於 8",
                        workspace=workspace_key,
                        page=page_path,
                        widget=type(view).__name__,
                    )
                if not fifth_visible:
                    _add_error(
                        evidence,
                        geometry_evidence,
                        code="fifth_synthetic_row_not_fully_visible",
                        message=(
                            f"合成資料第 5 列沒有完整落在 viewport；"
                            f"viewport={view.viewport().width()}x{view.viewport().height()}，"
                            f"row_rect={_rect_metrics(fifth_rect)}"
                        ),
                        workspace=workspace_key,
                        page=page_path,
                        widget=type(view).__name__,
                    )

                lower_index = fixture_model.index(stress_rows - 1, 0) if stress_rows else QModelIndex()
                vertical = view.verticalScrollBar()
                original_v_policy = _scroll_policy_name(view.verticalScrollBarPolicy())
                vertical.setValue(vertical.maximum())
                if lower_index.isValid():
                    view.scrollTo(lower_index, QAbstractItemView.ScrollHint.EnsureVisible)
                _wait_layout(view)
                lower_rect = view.visualRect(lower_index) if lower_index.isValid() else None
                lower_visible = bool(
                    lower_rect is not None
                    and lower_rect.isValid()
                    and lower_rect.bottom() >= 0
                    and lower_rect.top() < view.viewport().height()
                )
                lower_scrollable = bool(vertical.maximum() > 0)
                if lower_scrollable and original_v_policy == "AlwaysOff":
                    _add_error(
                        evidence,
                        geometry_evidence,
                        code="item_view_vertical_scroll_hidden",
                        message="fixture 有下方資料，但原始垂直 scrollbar policy 為 AlwaysOff",
                        workspace=workspace_key,
                        page=page_path,
                        widget=type(view).__name__,
                    )
                if not lower_visible:
                    _add_error(
                        evidence,
                        geometry_evidence,
                        code="lower_synthetic_row_unreachable",
                        message="捲動到下方後，最後一筆合成資料仍不在 viewport",
                        workspace=workspace_key,
                        page=page_path,
                        widget=type(view).__name__,
                    )

                horizontal_metrics = _stress_horizontal_scroll(
                    view,
                    fixture_model,
                    workspace_key,
                    page_path,
                    evidence,
                    geometry_evidence,
                )
                view.verticalScrollBar().setValue(0)
                view.horizontalScrollBar().setValue(0)
                _wait_layout(view)
                fixture_tip = _fixture_tooltip_evidence(fixture_model, view=view)
                if (
                    type(fixture_model).__name__ == "PandasTableModel"
                    and not fixture_tip.get("full_cell_text_available")
                ):
                    _add_error(
                        evidence,
                        geometry_evidence,
                        code="pandas_fixture_tooltip_missing",
                        message="合成 PandasTableModel 的長文字無法由 ToolTipRole 取得完整內容",
                        workspace=workspace_key,
                        page=page_path,
                        widget=view.objectName() or type(view).__name__,
                    )
                if isinstance(view, QTableView) and not isinstance(view, QTableWidget):
                    existing = evidence.get("pandas_tooltip_fixture")
                    if existing is None and type(fixture_model).__name__ == "PandasTableModel":
                        evidence["pandas_tooltip_fixture"] = fixture_tip
                fixture_screenshot = None
                if capture_fixture_screenshot and not page_entry.get("fixture_screenshot"):
                    _wait_layout(view)
                    path = geometry_dir / f"fixture_{_slug(page_path)}.png"
                    if _capture_widget(window, path):
                        fixture_screenshot = str(path)
                        page_entry["fixture_screenshot"] = fixture_screenshot
                        page_entry["fixture_screenshot_kind"] = "synthetic_first_rows_visible"
                        evidence["screenshots"].append(fixture_screenshot)
                entry["fixture_stress"] = {
                    "model_class": type(fixture_model).__name__,
                    "rows": stress_rows,
                    "columns": stress_columns,
                    "fifth_row_rect": _rect_metrics(fifth_rect),
                    "fifth_row_fully_visible": fifth_visible,
                    "minimum_height": int(view.minimumHeight()),
                    "actual_height": int(view.height()),
                    "viewport_size_logical": {
                        "width": int(view.viewport().width()),
                        "height": int(view.viewport().height()),
                    },
                    "visible_rows_helper": _visible_rows_helper_metrics(view),
                    "first_five_rows": _item_view_rows_metrics(view, stress_rows),
                    "vertical_scroll_maximum": int(vertical.maximum()),
                    "lower_row_index": stress_rows - 1,
                    "lower_row_rect_after_scroll": _rect_metrics(lower_rect),
                    "lower_row_scrollable": lower_scrollable,
                    "lower_row_reachable": lower_visible,
                    "vertical_scroll_policy": original_v_policy,
                    "horizontal_scroll": horizontal_metrics,
                    "tooltip": fixture_tip,
                    "fixture_screenshot": fixture_screenshot,
                    "fixture_data_is_synthetic": True,
                }
            restoration = fixture_info.get("restoration", {})
            entry["fixture_restoration"] = restoration
            entry["fixture_stress"]["restoration"] = restoration
            if "baseline_header_settle" in fixture_info:
                entry["fixture_stress"]["baseline_header_settle"] = fixture_info[
                    "baseline_header_settle"
                ]
            if "column_width_restore" in fixture_info:
                entry["fixture_stress"]["column_width_restore"] = fixture_info[
                    "column_width_restore"
                ]
            if "horizontal_header_state_readback" in fixture_info:
                entry["fixture_stress"]["horizontal_header_state_readback"] = fixture_info[
                    "horizontal_header_state_readback"
                ]
            _record_fixture_restoration_failure(
                fixture_info,
                evidence,
                geometry_evidence,
                workspace=workspace_key,
                page=page_path,
                widget=view.objectName() or type(view).__name__,
            )
        except _FixtureCoverageGap as exc:
            entry["supported"] = False
            entry["fixture_stress"] = {"skipped": True, "reason": str(exc)}
            gap = _finding(
                "coverage_gap",
                "synthetic_fixture_unsupported",
                str(exc),
                workspace_key,
                page_path,
                view.objectName() or type(view).__name__,
            )
            page_entry["coverage_gaps"].append(gap)
            geometry_evidence.setdefault("workspace_coverage_gaps", []).append(gap)
            evidence["coverage_gaps"].append(gap)
        except BaseException as exc:  # noqa: BLE001 - retain per-widget failure details
            _add_error(
                evidence,
                geometry_evidence,
                code="item_view_audit_exception",
                message=f"{type(exc).__name__}: {exc}",
                workspace=workspace_key,
                page=page_path,
                widget=view.objectName() or type(view).__name__,
            )


def _is_update_navigation_list(view: QWidget, page: QWidget) -> bool:
    # The native Update navigation list owns route selection. Its 12 real page
    # choices are measured as-is, because replacing it would change the route.
    if view.objectName() == "updateNavigationList":
        return True
    current: QWidget | None = view
    while current is not None:
        if getattr(current, "nav_list", None) is view:
            return True
        current = current.parentWidget()
    return False


def _inspect_baseline_long_cells(
    view: QWidget,
    entry: dict[str, Any],
    evidence: dict[str, Any],
    geometry_evidence: dict[str, Any],
    workspace_key: str,
    page_path: str,
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QAbstractItemView

    model = view.model()
    if model is None:
        return
    rows = min(_model_count(model, "rowCount"), 40)
    columns = min(_model_count(model, "columnCount"), 20)
    long_cells: list[dict[str, Any]] = []
    for row in range(rows):
        for column in range(columns):
            index = model.index(row, column)
            if not index.isValid():
                continue
            display = model.data(index, Qt.ItemDataRole.DisplayRole)
            if display is None:
                continue
            text = str(display)
            if len(text) < 80:
                continue
            tooltip = model.data(index, Qt.ItemDataRole.ToolTipRole)
            tip_text = str(tooltip) if tooltip is not None else ""
            full_tip = text in tip_text or len(tip_text) >= len(text)
            long_cells.append(
                {
                    "row": row,
                    "column": column,
                    "display_length": len(text),
                    "tooltip_length": len(tip_text),
                    "full_text_available_in_tooltip": full_tip,
                }
            )
            if not full_tip:
                _add_error(
                    evidence,
                    geometry_evidence,
                    code="baseline_long_cell_without_full_tooltip",
                    message=(
                        f"原 model 的長文字 cell ({row}, {column}) 有 {len(text)} 字，"
                        "ToolTipRole 未提供完整內容"
                    ),
                    workspace=workspace_key,
                    page=page_path,
                    widget=view.objectName() or type(view).__name__,
                )
    entry["baseline_model"]["long_text_cells"] = long_cells
    entry["baseline_model"]["long_text_cell_count"] = len(long_cells)
    if isinstance(view, QAbstractItemView) and columns:
        total_width = sum(int(view.columnWidth(column)) for column in range(columns))
        viewport_width = int(view.viewport().width())
        entry["baseline_model"]["total_column_width"] = total_width
        entry["baseline_model"]["viewport_width"] = viewport_width
        entry["baseline_model"]["columns_overflow_viewport"] = total_width > viewport_width
        if total_width > viewport_width:
            h_policy = entry["baseline_model"]["horizontal_scroll_policy"]
            entry["baseline_model"]["horizontal_overflow_has_full_tooltip"] = bool(
                long_cells and all(cell["full_text_available_in_tooltip"] for cell in long_cells)
            )
            if h_policy == "AlwaysOff" and not entry["baseline_model"]["horizontal_overflow_has_full_tooltip"]:
                _add_error(
                    evidence,
                    geometry_evidence,
                    code="baseline_overflow_not_reachable",
                    message="原 model 欄寬超過 viewport、水平捲軸被 AlwaysOff，且沒有完整長文字 tooltip",
                    workspace=workspace_key,
                    page=page_path,
                    widget=view.objectName() or type(view).__name__,
                )


def _synthetic_frame() -> Any:
    import pandas as pd

    headers = [
        "分點名稱",
        "買進張數",
        "賣出張數",
        "淨買賣超",
        LONG_HEADER_TEXT,
    ]
    rows = [
        [
            f"QA 合成分點 {index:03d}",
            index * 10,
            index * 7,
            index * 3,
            f"第 {index:03d} 筆。{LONG_CELL_TEXT}",
        ]
        for index in range(SYNTHETIC_ROW_COUNT)
    ]
    return pd.DataFrame(rows, columns=headers)


def _specialized_table_fixture(view: QWidget, original_model: Any, rows: int) -> Any | None:
    """Build data that is safe for delegates requiring typed model roles."""

    delegate_name = type(view.itemDelegate()).__name__ if hasattr(view, "itemDelegate") else ""
    if delegate_name != "TerminalScannerDelegate":
        return None

    from decision_module.flow_contracts import (
        BranchFlowAggregation,
        FlowSignalDTO,
        StockFlowAggregation,
    )
    from ui_qt.views.smart_money.terminal_table_model import (
        BranchTrackerTableModel,
        TerminalTableModel,
    )

    if isinstance(original_model, BranchTrackerTableModel):
        values = [
            BranchFlowAggregation(
                branch_system_key=f"qa-{row:03d}",
                branch_display_name=f"QA 合成分點 {row:03d}",
                stock_code=f"{2300 + row:04d}",
                stock_name=f"QA 公司 {row:03d}",
                total_buy_qty=1_000 + row,
                total_sell_qty=700 + row,
                total_net_qty=300 + row,
                sparkline_data=[float(point - row) for point in range(5)],
                sparkline_details=[(f"2026-09-{20 + point:02d}", point - row) for point in range(5)],
            )
            for row in range(rows)
        ]
        return BranchTrackerTableModel(values, view)

    signals = []
    for row in range(rows):
        stock_code = f"{2300 + row:04d}"
        aggregation = StockFlowAggregation(
            stock_code=stock_code,
            stock_name=f"QA 公司 {row:03d}",
            total_buy_qty=1_000 + row,
            total_sell_qty=700 + row,
            total_net_qty=300 + row,
        )
        signals.append(
            FlowSignalDTO(
                stock_code=stock_code,
                stock_name=f"QA 公司 {row:03d}",
                aggregation=aggregation,
                smart_money_score=75.0,
                confidence=0.8,
                signal_tags=["QA 合成訊號", "版面測試"],
                branch_concentration=0.35,
                sparkline_data=[float(point - row) for point in range(5)],
                sparkline_details=[(f"2026-09-{20 + point:02d}", point - row) for point in range(5)],
                intensity_level=1,
            )
        )
    return TerminalTableModel(signals, view)


class _FixtureCoverageGap(RuntimeError):
    pass


def _restoration_report(
    checks: dict[str, bool], *, restore_exception: str | None = None
) -> dict[str, Any]:
    failed_checks = [name for name, passed in checks.items() if not passed]
    if restore_exception:
        failed_checks.append("restore_exception")
    return {
        "passed": bool(checks) and not failed_checks,
        "checks": checks,
        "failed_checks": failed_checks,
        "restore_exception": restore_exception,
    }


def _same_item_identity(left: Any, right: Any) -> bool:
    if left is right:
        return True
    if left is None or right is None:
        return False
    try:
        from shiboken6 import getCppPointer

        return getCppPointer(left)[0] == getCppPointer(right)[0]
    except (ImportError, RuntimeError, TypeError, IndexError):
        return False


def _table_widget_header_content(view: Any) -> list[tuple[str, str] | None]:
    values: list[tuple[str, str] | None] = []
    for column in range(view.columnCount()):
        item = view.horizontalHeaderItem(column)
        values.append(None if item is None else (item.text(), item.toolTip()))
    return values


def _qt_enum_value(value: Any) -> int | str | None:
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        try:
            return int(enum_value)
        except (TypeError, ValueError):
            return str(enum_value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None if value is None else str(value)


def _header_state_contract(header: Any) -> dict[str, Any]:
    """Expose the stable, user-visible header state independent of section sizes."""
    count = int(header.count())
    optional_bool_fields = {
        "sections_movable": "sectionsMovable",
        "sections_clickable": "sectionsClickable",
        "highlight_sections": "highlightSections",
        "sort_indicator_shown": "isSortIndicatorShown",
        "cascading_section_resizes": "cascadingSectionResizes",
        "sort_indicator_clearable": "isSortIndicatorClearable",
        "first_section_movable": "isFirstSectionMovable",
    }
    contract: dict[str, Any] = {
        "count": count,
        "orientation": _qt_enum_value(header.orientation()),
        "visual_order": [int(header.logicalIndex(visual)) for visual in range(count)],
        "visual_index_by_logical": [int(header.visualIndex(logical)) for logical in range(count)],
        "resize_modes": [
            _qt_enum_value(header.sectionResizeMode(logical)) for logical in range(count)
        ],
        "hidden_sections": [bool(header.isSectionHidden(logical)) for logical in range(count)],
        "stretch_last_section": bool(header.stretchLastSection()),
        "minimum_section_size": int(header.minimumSectionSize()),
        "maximum_section_size": int(header.maximumSectionSize()),
        "default_section_size": int(header.defaultSectionSize()),
        "sort_indicator_section": int(header.sortIndicatorSection()),
        "sort_indicator_order": _qt_enum_value(header.sortIndicatorOrder()),
        "default_alignment": _qt_enum_value(header.defaultAlignment()),
        "text_elide_mode": _qt_enum_value(header.textElideMode()),
        "focus_policy": _qt_enum_value(header.focusPolicy()),
        "enabled": bool(header.isEnabled()),
    }
    for key, method_name in optional_bool_fields.items():
        getter = getattr(header, method_name, None)
        contract[key] = bool(getter()) if callable(getter) else None
    precision_getter = getattr(header, "resizeContentsPrecision", None)
    contract["resize_contents_precision"] = (
        int(precision_getter()) if callable(precision_getter) else None
    )
    context_menu_getter = getattr(header, "contextMenuPolicy", None)
    contract["context_menu_policy"] = (
        _qt_enum_value(context_menu_getter()) if callable(context_menu_getter) else None
    )
    return contract


def _compare_header_state_contract(
    expected: dict[str, Any], actual: dict[str, Any]
) -> dict[str, Any]:
    fields = sorted(set(expected) | set(actual))
    differences = {
        field: {"expected": expected.get(field), "actual": actual.get(field)}
        for field in fields
        if expected.get(field) != actual.get(field)
    }
    return {
        "passed": not differences,
        "failed_fields": list(differences),
        "differences": differences,
        "expected": expected,
        "actual": actual,
    }


def _header_state_readback(
    header: Any,
    *,
    original_state: Any,
    original_contract: dict[str, Any],
    restore_state_accepted: bool,
    column_width_readback: dict[str, Any],
) -> dict[str, Any]:
    current_contract = _header_state_contract(header)
    semantic = _compare_header_state_contract(original_contract, current_contract)
    serialized_equal = bytes(header.saveState()) == bytes(original_state)
    baseline_widths = list(column_width_readback.get("baseline_widths", []))
    restored_widths = list(column_width_readback.get("restored_widths", []))
    changed_width_sections = [
        column
        for column, (baseline, restored) in enumerate(zip(baseline_widths, restored_widths))
        if int(baseline) != int(restored)
    ]
    adaptive_columns = {
        int(column) for column in column_width_readback.get("dynamic_columns", [])
    }
    width_delta_is_adaptive = bool(changed_width_sections) and set(
        changed_width_sections
    ).issubset(adaptive_columns)
    serialization_difference_explained = bool(
        serialized_equal
        or (
            width_delta_is_adaptive
            and column_width_readback.get("passed") is True
        )
    )
    return {
        "passed": bool(
            restore_state_accepted
            and semantic["passed"]
            and serialization_difference_explained
        ),
        "restore_state_accepted": bool(restore_state_accepted),
        "serialized_equal": bool(serialized_equal),
        "serialization_difference_explained_by_adaptive_width": bool(
            serialization_difference_explained
        ),
        "changed_width_sections": changed_width_sections,
        "adaptive_width_sections": sorted(adaptive_columns),
        "semantic_contract": semantic,
    }


def _table_widget_cell_content(view: Any) -> list[tuple[int, int, str, str] | tuple[int, int, None, None]]:
    values: list[tuple[int, int, str, str] | tuple[int, int, None, None]] = []
    for row in range(view.rowCount()):
        for column in range(view.columnCount()):
            item = view.item(row, column)
            values.append(
                (row, column, None, None)
                if item is None
                else (row, column, item.text(), item.toolTip())
            )
    return values


def _table_widget_column_width_readback(
    view: Any,
    *,
    original_widths: list[int],
    original_resize_modes: list[int],
    original_hidden_sections: list[bool],
    original_stretch_last_section: bool,
    baseline_viewport_width: int,
    baseline_header_viewport_width: int,
    fixture_viewport_width: int,
    fixture_header_viewport_width: int,
) -> dict[str, Any]:
    """Validate restored table widths without treating adaptive sections as fixed.

    QTableWidget may gain or lose a vertical scrollbar while synthetic rows are
    installed. That changes the horizontal header's viewport width. Fixed and
    interactive sections retain their exact widths; ResizeToContents sections
    retain their original content width; Stretch and stretch-last sections are
    checked against the final viewport's available width.
    """
    from PySide6.QtWidgets import QHeaderView

    header = view.horizontalHeader()
    actual_widths = [int(view.columnWidth(column)) for column in range(len(original_widths))]
    actual_modes = [
        int(header.sectionResizeMode(column).value)
        for column in range(len(original_resize_modes))
    ]
    visible_columns = [
        column
        for column in range(len(original_widths))
        if not bool(header.isSectionHidden(column))
    ]
    last_visible_column = (
        max(visible_columns, key=lambda column: int(header.visualIndex(column)))
        if visible_columns
        else None
    )
    dynamic_columns: list[int] = []
    dynamic_width_floors: dict[int, int] = {}
    per_column: list[dict[str, Any]] = []
    fixed_widths_passed = True
    natural_widths_passed = True

    mode_names = {
        QHeaderView.ResizeMode.Interactive.value: "Interactive",
        QHeaderView.ResizeMode.Stretch.value: "Stretch",
        QHeaderView.ResizeMode.Fixed.value: "Fixed",
        QHeaderView.ResizeMode.ResizeToContents.value: "ResizeToContents",
    }
    modes_restored = actual_modes == original_resize_modes
    hidden_restored = [
        bool(header.isSectionHidden(column)) for column in range(len(original_widths))
    ] == original_hidden_sections
    stretch_last_section_restored = (
        bool(header.stretchLastSection()) == original_stretch_last_section
    )
    for column, (expected_width, actual_width, mode, actual_mode, hidden) in enumerate(
        zip(
            original_widths,
            actual_widths,
            original_resize_modes,
            actual_modes,
            original_hidden_sections,
        )
    ):
        is_last_stretched = bool(
            original_stretch_last_section
            and column == last_visible_column
            and not hidden
        )
        is_stretch_mode = mode == QHeaderView.ResizeMode.Stretch.value
        natural_width_hint = int(view.sizeHintForColumn(column)) if not hidden else 0
        if hidden:
            passed = bool(header.isSectionHidden(column))
            rule = "hidden_section_state"
        elif is_last_stretched or is_stretch_mode:
            dynamic_columns.append(column)
            minimum_width = int(header.minimumSectionSize())
            section_floor = max(
                minimum_width,
                expected_width if is_last_stretched else minimum_width,
            )
            dynamic_width_floors[column] = section_floor
            passed = actual_width >= section_floor
            rule = "viewport_allocation"
        elif mode in (
            QHeaderView.ResizeMode.Fixed.value,
            QHeaderView.ResizeMode.Interactive.value,
        ):
            passed = actual_width == expected_width
            fixed_widths_passed = fixed_widths_passed and passed
            rule = "exact_user_width"
        elif mode == QHeaderView.ResizeMode.ResizeToContents.value:
            passed = actual_width == expected_width and actual_width >= natural_width_hint
            natural_widths_passed = natural_widths_passed and passed
            rule = "original_content_width_and_size_hint"
        else:
            # Unknown future Qt modes must not silently weaken restoration.
            passed = actual_width == expected_width
            fixed_widths_passed = fixed_widths_passed and passed
            rule = "exact_fallback_for_unknown_mode"
        per_column.append(
            {
                "column": column,
                "mode": mode_names.get(mode, f"Unknown({mode})"),
                "restored_mode": mode_names.get(actual_mode, f"Unknown({actual_mode})"),
                "hidden": hidden,
                "stretch_last_section_override": is_last_stretched,
                "width_rule": rule,
                "baseline_width": expected_width,
                "restored_width": actual_width,
                "restored_size_hint": natural_width_hint,
                "passed": bool(passed),
            }
        )

    header_viewport_width = int(header.viewport().width())
    dynamic_expected_width = (
        max(
            sum(dynamic_width_floors.values()),
            header_viewport_width
            - sum(
                actual_widths[column]
                for column in visible_columns
                if column not in dynamic_columns
            ),
        )
        if dynamic_columns
        else 0
    )
    dynamic_actual_width = sum(actual_widths[column] for column in dynamic_columns)
    viewport_allocation_passed = (
        not dynamic_columns
        or abs(dynamic_actual_width - dynamic_expected_width) <= max(1, len(dynamic_columns))
    )
    for entry in per_column:
        if entry["width_rule"] == "viewport_allocation":
            entry["passed"] = bool(entry["passed"] and viewport_allocation_passed)

    return {
        "passed": bool(
            fixed_widths_passed
            and natural_widths_passed
            and viewport_allocation_passed
            and modes_restored
            and hidden_restored
            and stretch_last_section_restored
            and all(entry["passed"] for entry in per_column)
        ),
        "baseline_widths": original_widths,
        "restored_widths": actual_widths,
        "baseline_resize_modes": [mode_names.get(mode, f"Unknown({mode})") for mode in original_resize_modes],
        "restored_resize_modes": [mode_names.get(mode, f"Unknown({mode})") for mode in actual_modes],
        "baseline_hidden_sections": original_hidden_sections,
        "restored_hidden_sections": [bool(header.isSectionHidden(column)) for column in range(len(original_widths))],
        "last_visible_column_logical_index": last_visible_column,
        "last_visible_column_visual_index": (
            int(header.visualIndex(last_visible_column))
            if last_visible_column is not None
            else None
        ),
        "resize_modes_restored": bool(modes_restored),
        "hidden_sections_restored": bool(hidden_restored),
        "stretch_last_section_restored": bool(stretch_last_section_restored),
        "baseline_viewport_width": baseline_viewport_width,
        "fixture_viewport_width_before_restore": fixture_viewport_width,
        "restored_viewport_width": int(view.viewport().width()),
        "baseline_header_viewport_width": baseline_header_viewport_width,
        "fixture_header_viewport_width_before_restore": fixture_header_viewport_width,
        "restored_header_viewport_width": header_viewport_width,
        "stretch_last_section": bool(header.stretchLastSection()),
        "dynamic_columns": dynamic_columns,
        "dynamic_section_width_floors": dynamic_width_floors,
        "dynamic_expected_total_width": dynamic_expected_width,
        "dynamic_restored_total_width": dynamic_actual_width,
        "fixed_widths_passed": bool(fixed_widths_passed),
        "natural_widths_passed": bool(natural_widths_passed),
        "viewport_allocation_passed": bool(viewport_allocation_passed),
        "per_column": per_column,
    }


def _record_fixture_restoration_failure(
    fixture_info: dict[str, Any],
    evidence: dict[str, Any],
    geometry_evidence: dict[str, Any],
    *,
    workspace: str,
    page: str,
    widget: str,
) -> None:
    restoration = fixture_info.get("restoration")
    if isinstance(restoration, dict) and restoration.get("passed") is True:
        return
    failed_checks = (
        restoration.get("failed_checks", [])
        if isinstance(restoration, dict)
        else ["restoration_result_missing"]
    )
    detail = ", ".join(str(name) for name in failed_checks) or "unknown restoration failure"
    restore_exception = (
        restoration.get("restore_exception") if isinstance(restoration, dict) else None
    )
    if restore_exception:
        detail = f"{detail}; restore error: {restore_exception}"
    _add_error(
        evidence,
        geometry_evidence,
        code="synthetic_fixture_restore_failed",
        message=f"合成資料 fixture 還原檢查失敗：{detail}",
        workspace=workspace,
        page=page,
        widget=widget,
    )


@contextmanager
def _synthetic_view_data(view: QWidget, *, rows: int) -> Iterator[dict[str, Any]]:
    from PySide6.QtCore import QModelIndex, QStringListModel
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QHeaderView,
        QListWidget,
        QTableView,
        QTableWidget,
        QTreeView,
        QTreeWidget,
    )
    from ui_qt.models.pandas_table_model import PandasTableModel

    original_model = view.model() if isinstance(view, QAbstractItemView) else None
    original_index = view.currentIndex() if isinstance(view, QAbstractItemView) else None
    original_row = original_index.row() if original_index is not None and original_index.isValid() else -1
    original_column = original_index.column() if original_index is not None and original_index.isValid() else 0
    old_h_value = int(view.horizontalScrollBar().value()) if isinstance(view, QAbstractItemView) else 0
    old_v_value = int(view.verticalScrollBar().value()) if isinstance(view, QAbstractItemView) else 0
    metadata: dict[str, Any] = {"rows": rows}

    if isinstance(view, QTableWidget):
        if any(
            view.cellWidget(row, column) is not None
            for row in range(view.rowCount())
            for column in range(view.columnCount())
        ):
            raise _FixtureCoverageGap("QTableWidget 含有 cellWidget；不安全替換，請以該元件專屬 fixture 測試")
        _wait_layout(view)
        header_for_baseline = view.horizontalHeader()
        pre_settle_widths = [
            int(view.columnWidth(column)) for column in range(view.columnCount())
        ]
        pre_settle_modes = [
            int(header_for_baseline.sectionResizeMode(column).value)
            for column in range(view.columnCount())
        ]
        header_for_baseline.resizeSections()
        _wait_layout(view)
        post_settle_widths = [
            int(view.columnWidth(column)) for column in range(view.columnCount())
        ]
        post_settle_modes = [
            int(header_for_baseline.sectionResizeMode(column).value)
            for column in range(view.columnCount())
        ]
        user_width_modes = {
            QHeaderView.ResizeMode.Interactive.value,
            QHeaderView.ResizeMode.Fixed.value,
        }
        baseline_settle_user_widths_preserved = all(
            pre_settle_widths[column] == post_settle_widths[column]
            for column, mode in enumerate(pre_settle_modes)
            if mode in user_width_modes
        )
        baseline_settle_modes_preserved = pre_settle_modes == post_settle_modes
        metadata["baseline_header_settle"] = {
            "operation": "QHeaderView.resizeSections() using each section's current mode",
            "before_widths": pre_settle_widths,
            "after_widths": post_settle_widths,
            "resize_modes_before": pre_settle_modes,
            "resize_modes_after": post_settle_modes,
            "fixed_interactive_widths_preserved": baseline_settle_user_widths_preserved,
            "resize_modes_preserved": baseline_settle_modes_preserved,
        }
        original_current_row = int(view.currentRow())
        original_current_column = int(view.currentColumn())
        original_row_count = view.rowCount()
        original_column_count = view.columnCount()
        original_row_heights = [int(view.rowHeight(row)) for row in range(original_row_count)]
        original_column_widths = [int(view.columnWidth(column)) for column in range(original_column_count)]
        original_resize_modes = [
            int(view.horizontalHeader().sectionResizeMode(column).value)
            for column in range(original_column_count)
        ]
        original_hidden_sections = [
            bool(view.horizontalHeader().isSectionHidden(column))
            for column in range(original_column_count)
        ]
        original_stretch_last_section = bool(view.horizontalHeader().stretchLastSection())
        original_viewport_width = int(view.viewport().width())
        original_header_viewport_width = int(view.horizontalHeader().viewport().width())
        original_cell_items = [
            (row, column, view.item(row, column))
            for row in range(original_row_count)
            for column in range(original_column_count)
        ]
        original_cell_content = _table_widget_cell_content(view)
        original_headers = [
            view.horizontalHeaderItem(column).clone()
            if view.horizontalHeaderItem(column)
            else None
            for column in range(original_column_count)
        ]
        original_header_content = _table_widget_header_content(view)
        original_horizontal_header_state = view.horizontalHeader().saveState()
        original_horizontal_header_contract = _header_state_contract(
            view.horizontalHeader()
        )
        original_vertical_header_state = view.verticalHeader().saveState()
        original_sorting = bool(view.isSortingEnabled())
        original_sort_column = int(view.horizontalHeader().sortIndicatorSection())
        original_sort_order = view.horizontalHeader().sortIndicatorOrder()
        original_items: list[tuple[int, int, Any]] = []
        restore_exception: str | None = None
        horizontal_state_restored = False
        vertical_state_restored = False
        fixture_viewport_width_before_restore = 0
        fixture_header_viewport_width_before_restore = 0
        column_width_readback: dict[str, Any] = {}
        horizontal_header_state_readback: dict[str, Any] = {}
        with _blocked_view_and_selection_signals(view) as block_current_selection:
            try:
                # Detach original objects only after both the view and its
                # selection model are blocked. Model signals stay live so Qt
                # layout/row measurement still runs against the fixture.
                original_items = [
                    (row, column, view.takeItem(row, column))
                    for row in range(original_row_count)
                    for column in range(original_column_count)
                ]
                view.setSortingEnabled(False)
                view.setRowCount(rows)
                view.setColumnCount(max(original_column_count, 5))
                for column, label in enumerate(_synthetic_frame().columns):
                    if column < view.columnCount():
                        from PySide6.QtWidgets import QTableWidgetItem

                        view.setHorizontalHeaderItem(column, QTableWidgetItem(str(label)))
                for row in range(rows):
                    for column in range(view.columnCount()):
                        text = LONG_CELL_TEXT if column == view.columnCount() - 1 else f"QA-{row:03d}｜合成欄 {column + 1}"
                        from PySide6.QtWidgets import QTableWidgetItem

                        item = QTableWidgetItem(text)
                        item.setToolTip(text)
                        view.setItem(row, column, item)
                block_current_selection()
                yield metadata
            finally:
                try:
                    fixture_viewport_width_before_restore = int(view.viewport().width())
                    fixture_header_viewport_width_before_restore = int(
                        view.horizontalHeader().viewport().width()
                    )
                    view.setSortingEnabled(False)
                    view.clearContents()
                    view.setRowCount(original_row_count)
                    view.setColumnCount(original_column_count)
                    for item_row, item_column, item in original_items:
                        if item is not None and item_row < original_row_count and item_column < original_column_count:
                            view.setItem(item_row, item_column, item)
                    for column, header in enumerate(original_headers):
                        if header is not None and column < original_column_count:
                            view.setHorizontalHeaderItem(column, header)
                    for column, width in enumerate(original_column_widths):
                        if column < original_column_count:
                            view.setColumnWidth(column, width)
                    for row, row_height in enumerate(original_row_heights):
                        view.setRowHeight(row, row_height)
                    horizontal_state_restored = bool(
                        view.horizontalHeader().restoreState(original_horizontal_header_state)
                    )
                    vertical_state_restored = bool(
                        view.verticalHeader().restoreState(original_vertical_header_state)
                    )
                    view.horizontalHeader().setSortIndicator(original_sort_column, original_sort_order)
                    if original_sorting:
                        view.setSortingEnabled(True)
                    if (
                        0 <= original_current_row < view.rowCount()
                        and 0 <= original_current_column < view.columnCount()
                    ):
                        view.setCurrentCell(original_current_row, original_current_column)
                    else:
                        view.setCurrentCell(-1, -1)
                    view.verticalScrollBar().setValue(old_v_value)
                    view.horizontalScrollBar().setValue(old_h_value)
                except Exception as exc:  # noqa: BLE001 - report restoration as evidence
                    restore_exception = f"{type(exc).__name__}: {exc}"
        _wait_layout(view)
        try:
            column_width_readback = _table_widget_column_width_readback(
                view,
                original_widths=original_column_widths,
                original_resize_modes=original_resize_modes,
                original_hidden_sections=original_hidden_sections,
                original_stretch_last_section=original_stretch_last_section,
                baseline_viewport_width=original_viewport_width,
                baseline_header_viewport_width=original_header_viewport_width,
                fixture_viewport_width=fixture_viewport_width_before_restore,
                fixture_header_viewport_width=fixture_header_viewport_width_before_restore,
            )
            horizontal_header_state_readback = _header_state_readback(
                view.horizontalHeader(),
                original_state=original_horizontal_header_state,
                original_contract=original_horizontal_header_contract,
                restore_state_accepted=horizontal_state_restored,
                column_width_readback=column_width_readback,
            )
            checks = {
                "model_identity": view.model() is original_model,
                "row_count": view.rowCount() == original_row_count,
                "column_count": view.columnCount() == original_column_count,
                "cell_identity": all(
                    _same_item_identity(view.item(row, column), item)
                    for row, column, item in original_cell_items
                ),
                "cell_text_tooltip": _table_widget_cell_content(view) == original_cell_content,
                "header_text_tooltip": _table_widget_header_content(view) == original_header_content,
                "horizontal_header_state": bool(
                    horizontal_header_state_readback.get("passed", False)
                ),
                "vertical_header_state": (
                    vertical_state_restored
                    and bytes(view.verticalHeader().saveState())
                    == bytes(original_vertical_header_state)
                ),
                "column_widths": bool(column_width_readback.get("passed", False)),
                "baseline_settle_user_widths_preserved": bool(
                    baseline_settle_user_widths_preserved
                ),
                "baseline_settle_resize_modes_preserved": bool(
                    baseline_settle_modes_preserved
                ),
                "column_resize_modes": bool(
                    column_width_readback.get("resize_modes_restored", False)
                ),
                "column_visibility": bool(
                    column_width_readback.get("hidden_sections_restored", False)
                ),
                "stretch_last_section": bool(
                    column_width_readback.get("stretch_last_section_restored", False)
                ),
                "row_heights": [
                    int(view.rowHeight(row)) for row in range(original_row_count)
                ] == original_row_heights,
                "sorting_enabled": bool(view.isSortingEnabled()) == original_sorting,
                "sort_indicator": (
                    int(view.horizontalHeader().sortIndicatorSection()) == original_sort_column
                    and view.horizontalHeader().sortIndicatorOrder() == original_sort_order
                ),
                "current_cell": (
                    view.currentRow() == original_current_row
                    and view.currentColumn() == original_current_column
                ),
                "vertical_scroll": int(view.verticalScrollBar().value()) == old_v_value,
                "horizontal_scroll": int(view.horizontalScrollBar().value()) == old_h_value,
            }
        except Exception as exc:  # noqa: BLE001 - incomplete readback is a failed check
            checks = {"restoration_readback": False}
            readback_error = f"{type(exc).__name__}: {exc}"
            restore_exception = "; ".join(
                part for part in (restore_exception, readback_error) if part
            )
        metadata["restoration"] = _restoration_report(
            checks, restore_exception=restore_exception
        )
        metadata["column_width_restore"] = column_width_readback
        metadata["horizontal_header_state_readback"] = horizontal_header_state_readback
        return

    if isinstance(view, QTreeWidget):
        if any(
            view.itemWidget(item, column) is not None
            for item in _tree_items(view)
            for column in range(view.columnCount())
        ):
            raise _FixtureCoverageGap("QTreeWidget 含有 itemWidget；不安全替換，請以該元件專屬 fixture 測試")
        original_headers = [view.headerItem().clone()] if view.headerItem() is not None else []
        original_column_count = view.columnCount()
        original_column_widths = [int(view.columnWidth(column)) for column in range(original_column_count)]
        original_header_item = view.headerItem()
        original_header_content = (
            [
                (original_header_item.text(column), original_header_item.toolTip(column))
                for column in range(original_column_count)
            ]
            if original_header_item is not None
            else []
        )
        del original_header_item
        original_header_state = view.header().saveState()
        original_tree_items = _tree_items(view)
        original_top_level_items = [
            view.topLevelItem(index) for index in range(view.topLevelItemCount())
        ]
        original_current_item = view.currentItem()
        original_sorting = bool(view.isSortingEnabled())
        original_sort_column = int(view.sortColumn())
        original_sort_order = view.header().sortIndicatorOrder()
        original_items: list[Any] = []
        restore_exception = None
        header_state_restored = False
        with _blocked_view_and_selection_signals(view) as block_current_selection:
            try:
                original_items = [view.takeTopLevelItem(0) for _ in range(view.topLevelItemCount())]
                view.setColumnCount(max(original_column_count, 5))
                view.setHeaderLabels([str(label) for label in list(_synthetic_frame().columns)[: view.columnCount()]])
                for row in range(rows):
                    from PySide6.QtWidgets import QTreeWidgetItem

                    item = QTreeWidgetItem([f"QA-{row:03d}", f"合成狀態 {row:03d}", "2026-09-29", "版面測試", LONG_CELL_TEXT])
                    for column in range(item.columnCount()):
                        item.setToolTip(column, item.text(column))
                    view.addTopLevelItem(item)
                block_current_selection()
                yield metadata
            finally:
                try:
                    view.setSortingEnabled(False)
                    view.clear()
                    view.setColumnCount(original_column_count)
                    if original_headers:
                        view.setHeaderItem(original_headers[0])
                    for item in original_items:
                        if item is not None:
                            view.addTopLevelItem(item)
                    for column, width in enumerate(original_column_widths):
                        view.setColumnWidth(column, width)
                    header_state_restored = bool(view.header().restoreState(original_header_state))
                    view.header().setSortIndicator(original_sort_column, original_sort_order)
                    if original_sorting:
                        view.setSortingEnabled(True)
                    if original_current_item is not None:
                        view.setCurrentItem(original_current_item, original_column)
                    view.verticalScrollBar().setValue(old_v_value)
                    view.horizontalScrollBar().setValue(old_h_value)
                except Exception as exc:  # noqa: BLE001 - report restoration as evidence
                    restore_exception = f"{type(exc).__name__}: {exc}"
        try:
            restored_header = view.headerItem()
            restored_header_content = (
                [
                    (restored_header.text(column), restored_header.toolTip(column))
                    for column in range(view.columnCount())
                ]
                if restored_header is not None
                else []
            )
            checks = {
                "model_identity": view.model() is original_model,
                "column_count": view.columnCount() == original_column_count,
                "top_level_item_identity": all(
                    _same_item_identity(view.topLevelItem(index), item)
                    for index, item in enumerate(original_top_level_items)
                )
                and view.topLevelItemCount() == len(original_top_level_items),
                "tree_item_identity": all(
                    _same_item_identity(current, original)
                    for current, original in zip(_tree_items(view), original_tree_items)
                )
                and len(_tree_items(view)) == len(original_tree_items),
                "header_text_tooltip": restored_header_content == original_header_content,
                "header_state": (
                    header_state_restored
                    and bytes(view.header().saveState())
                    == bytes(original_header_state)
                ),
                "column_widths": [
                    int(view.columnWidth(column)) for column in range(original_column_count)
                ] == original_column_widths,
                "sorting_enabled": bool(view.isSortingEnabled()) == original_sorting,
                "sort_indicator": (
                    int(view.sortColumn()) == original_sort_column
                    and view.header().sortIndicatorOrder() == original_sort_order
                ),
                "current_item_identity": _same_item_identity(
                    view.currentItem(), original_current_item
                ),
                "vertical_scroll": int(view.verticalScrollBar().value()) == old_v_value,
                "horizontal_scroll": int(view.horizontalScrollBar().value()) == old_h_value,
            }
        except Exception as exc:  # noqa: BLE001 - incomplete readback is a failed check
            checks = {"restoration_readback": False}
            readback_error = f"{type(exc).__name__}: {exc}"
            restore_exception = "; ".join(
                part for part in (restore_exception, readback_error) if part
            )
        metadata["restoration"] = _restoration_report(
            checks, restore_exception=restore_exception
        )
        return

    if isinstance(view, QListWidget):
        original_items = [view.item(row) for row in range(view.count())]
        if any(view.itemWidget(item) is not None for item in original_items if item is not None):
            raise _FixtureCoverageGap(
                "QListWidget 含有 itemWidget；fixture 未改動該清單，需以保留元件的 additive fixture 驗證"
            )
        original_sorting = bool(view.isSortingEnabled())
        original_item_content = [
            (item.text(), item.toolTip()) if item is not None else None
            for item in original_items
        ]
        restore_exception = None
        with _blocked_view_and_selection_signals(view) as block_current_selection:
            try:
                original_items = [view.takeItem(0) for _ in range(view.count())]
                view.setSortingEnabled(False)
                for row in range(rows):
                    from PySide6.QtWidgets import QListWidgetItem

                    item = QListWidgetItem(f"QA-{row:03d}｜{LONG_CELL_TEXT}")
                    item.setToolTip(item.text())
                    view.addItem(item)
                block_current_selection()
                yield metadata
            finally:
                try:
                    view.clear()
                    for item in original_items:
                        if item is not None:
                            view.addItem(item)
                    if original_sorting:
                        view.setSortingEnabled(True)
                    if 0 <= original_row < view.count():
                        view.setCurrentRow(original_row)
                    view.verticalScrollBar().setValue(old_v_value)
                    view.horizontalScrollBar().setValue(old_h_value)
                except Exception as exc:  # noqa: BLE001 - report restoration as evidence
                    restore_exception = f"{type(exc).__name__}: {exc}"
        try:
            restored_items = [view.item(row) for row in range(view.count())]
            checks = {
                "model_identity": view.model() is original_model,
                "item_count": view.count() == len(original_items),
                "item_identity": len(restored_items) == len(original_items)
                and all(
                    _same_item_identity(current, original)
                    for current, original in zip(restored_items, original_items)
                ),
                "item_text_tooltip": [
                    (item.text(), item.toolTip()) if item is not None else None
                    for item in restored_items
                ] == original_item_content,
                "current_row": view.currentRow() == original_row,
                "sorting_enabled": bool(view.isSortingEnabled()) == original_sorting,
                "vertical_scroll": int(view.verticalScrollBar().value()) == old_v_value,
                "horizontal_scroll": int(view.horizontalScrollBar().value()) == old_h_value,
                "item_widgets_absent": all(
                    view.itemWidget(item) is None for item in restored_items if item is not None
                ),
            }
        except Exception as exc:  # noqa: BLE001 - incomplete readback is a failed check
            checks = {"restoration_readback": False}
            readback_error = f"{type(exc).__name__}: {exc}"
            restore_exception = "; ".join(
                part for part in (restore_exception, readback_error) if part
            )
        metadata["restoration"] = _restoration_report(
            checks, restore_exception=restore_exception
        )
        return

    if isinstance(view, QTableView) or isinstance(view, QTreeView):
        fixture = _specialized_table_fixture(view, original_model, rows)
        delegate_name = type(view.itemDelegate()).__name__ if hasattr(view, "itemDelegate") else ""
        if delegate_name not in {"", "QStyledItemDelegate", "TerminalScannerDelegate", "DetailTableDelegate"}:
            raise _FixtureCoverageGap(
                f"自訂 delegate {delegate_name} 未登錄安全合成 model；請加專屬 typed fixture"
            )
        if fixture is None:
            fixture = PandasTableModel(_synthetic_frame())
    else:
        fixture = QStringListModel(
            [f"QA-{row:03d}｜{LONG_CELL_TEXT}" for row in range(rows)],
            view,
        )
    restore_exception = None
    with _blocked_view_and_selection_signals(view) as block_current_selection:
        try:
            view.setModel(fixture)
            block_current_selection()
            yield metadata
        finally:
            try:
                view.setModel(original_model)
                block_current_selection()
                if original_model is not None and original_row >= 0:
                    restored_index = original_model.index(original_row, original_column)
                    if restored_index.isValid():
                        view.setCurrentIndex(restored_index)
                view.verticalScrollBar().setValue(old_v_value)
                view.horizontalScrollBar().setValue(old_h_value)
            except Exception as exc:  # noqa: BLE001 - report restoration as evidence
                restore_exception = f"{type(exc).__name__}: {exc}"
    try:
        current_index = view.currentIndex()
        current_index_restored = (
            current_index.isValid()
            and current_index.row() == original_row
            and current_index.column() == original_column
            if original_row >= 0
            else not current_index.isValid()
        )
        checks = {
            "model_identity": view.model() is original_model,
            "current_index": current_index_restored,
            "vertical_scroll": int(view.verticalScrollBar().value()) == old_v_value,
            "horizontal_scroll": int(view.horizontalScrollBar().value()) == old_h_value,
        }
    except Exception as exc:  # noqa: BLE001 - incomplete readback is a failed check
        checks = {"restoration_readback": False}
        readback_error = f"{type(exc).__name__}: {exc}"
        restore_exception = "; ".join(
            part for part in (restore_exception, readback_error) if part
        )
    metadata["restoration"] = _restoration_report(
        checks, restore_exception=restore_exception
    )


@contextmanager
def _blocked_view_and_selection_signals(view: QWidget) -> Iterator[Any]:
    """Block UI selection callbacks while leaving synthetic model signals live."""

    original_view_blocked = view.blockSignals(True)
    selection_states: list[tuple[Any, bool]] = []

    def block_current_selection() -> None:
        selection_getter = getattr(view, "selectionModel", None)
        if not callable(selection_getter):
            return
        selection = selection_getter()
        if selection is None or any(current is selection for current, _state in selection_states):
            return
        selection_states.append((selection, bool(selection.blockSignals(True))))

    block_current_selection()
    try:
        yield block_current_selection
    finally:
        block_current_selection()
        for selection, was_blocked in selection_states:
            try:
                selection.blockSignals(was_blocked)
            except RuntimeError:
                continue
        view.blockSignals(original_view_blocked)


def _tree_items(tree: QWidget) -> list[Any]:
    items: list[Any] = []
    count = getattr(tree, "topLevelItemCount", lambda: 0)()
    stack = [tree.topLevelItem(index) for index in range(count)]
    while stack:
        item = stack.pop()
        if item is None:
            continue
        items.append(item)
        stack.extend(item.child(index) for index in range(item.childCount()))
    return items


def _stress_horizontal_scroll(
    view: QWidget,
    model: Any,
    workspace_key: str,
    page_path: str,
    evidence: dict[str, Any],
    geometry_evidence: dict[str, Any],
) -> dict[str, Any]:
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QListView

    if not isinstance(view, QAbstractItemView):
        return {"applicable": False, "reason": "not_an_item_view"}
    if _model_count(model, "columnCount") < 2 or isinstance(view, QListView):
        return {"applicable": False, "reason": "view_has_no_table_columns"}
    policy = _scroll_policy_name(view.horizontalScrollBarPolicy())
    section_count = _model_count(model, "columnCount")
    header = view.horizontalHeader() if hasattr(view, "horizontalHeader") else None
    if header is None:
        return {"applicable": False, "reason": "view_has_no_horizontal_header"}
    original_widths = [int(view.columnWidth(column)) for column in range(section_count)]
    original_mode_enums = [header.sectionResizeMode(column) for column in range(section_count)]
    original_modes = [mode.value for mode in original_mode_enums]
    header_state = header.saveState()
    widths = [160, 240, 320, 480, 1500]
    maximum = 0
    last_rect = None
    last_column_reachable = False
    scrollbar_visible = False
    try:
        for column in range(section_count):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            view.setColumnWidth(column, widths[min(column, len(widths) - 1)])
        _wait_layout(view)
        bar = view.horizontalScrollBar()
        maximum = int(bar.maximum())
        bar.setValue(maximum)
        _wait_layout(view)
        last_index = model.index(0, section_count - 1)
        last_rect = view.visualRect(last_index) if last_index.isValid() else None
        last_column_reachable = bool(
            last_rect is not None
            and last_rect.isValid()
            and last_rect.right() >= 0
            and last_rect.left() < view.viewport().width()
        )
        scrollbar_visible = bool(bar.isVisible())
        if maximum > 0 and policy == "AlwaysOff":
            _add_error(
                evidence,
                geometry_evidence,
                code="fixture_horizontal_scroll_hidden",
                message="寬欄 stress fixture 需要水平捲動，但原 widget policy 為 AlwaysOff",
                workspace=workspace_key,
                page=page_path,
                widget=view.objectName() or type(view).__name__,
            )
        if maximum <= 0 or not last_column_reachable:
            _add_error(
                evidence,
                geometry_evidence,
                code="fixture_horizontal_scroll_unreachable",
                message=(
                    "寬欄 stress fixture 無法水平移動到最右欄："
                    f"range={maximum}, last_column_reachable={last_column_reachable}"
                ),
                workspace=workspace_key,
                page=page_path,
                widget=view.objectName() or type(view).__name__,
            )
    finally:
        header.restoreState(header_state)
        view.horizontalScrollBar().setValue(0)
        _wait_layout(view)
    return {
        "applicable": True,
        "mode": "fixture_stress_forced_section_widths_not_baseline_pass",
        "horizontal_scroll_policy": policy,
        "forced_section_widths_logical": [
            int(widths[min(column, len(widths) - 1)]) for column in range(section_count)
        ],
        "baseline_section_widths_logical": original_widths,
        "baseline_section_resize_modes": original_modes,
        "scroll_range_maximum": maximum,
        "scrollbar_visible_at_right_edge": scrollbar_visible,
        "last_column_rect_at_right_edge": _rect_metrics(last_rect),
        "last_column_reachable": last_column_reachable,
        "section_widths_restored": [int(view.columnWidth(column)) for column in range(section_count)] == original_widths,
        "section_resize_modes_restored": [header.sectionResizeMode(column).value for column in range(section_count)] == original_modes,
        "tooltip_is_separately_checked": True,
    }


def _fixture_tooltip_evidence(model: Any, *, view: Any | None = None) -> dict[str, Any]:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListView, QListWidget, QTableView

    row_count = view.count() if isinstance(view, QListWidget) else _model_count(model, "rowCount")
    if row_count <= 0:
        return {"available": False, "reason": "fixture_model_empty", "row_count": row_count}

    if isinstance(view, QListWidget):
        item = view.item(0)
        display_text = item.text() if item is not None else ""
        tooltip_text = item.toolTip() if item is not None else ""
        complete = bool(
            display_text
            and (display_text in tooltip_text or len(tooltip_text) >= len(display_text))
        )
        return {
            "available": True,
            "model_class": type(model).__name__,
            "source": "QListWidgetItem",
            "row_count": row_count,
            "display_length": len(display_text),
            "tooltip_length": len(tooltip_text),
            "full_cell_text_available": complete,
            "header_applicable": False,
        }

    column_count = _model_count(model, "columnCount")
    if isinstance(view, QListView):
        column = 0
    else:
        column = max(0, column_count - 1)
    root_index = view.rootIndex() if view is not None and hasattr(view, "rootIndex") else None
    index = model.index(0, column, root_index) if root_index is not None else model.index(0, column)
    display = model.data(index, Qt.ItemDataRole.DisplayRole)
    tooltip = model.data(index, Qt.ItemDataRole.ToolTipRole)
    display_text = str(display) if display is not None else ""
    tooltip_text = str(tooltip) if tooltip is not None else ""
    complete = bool(display_text and (display_text in tooltip_text or len(tooltip_text) >= len(display_text)))
    header_applicable = isinstance(view, QTableView) or column_count > 1
    header_text = ""
    if header_applicable:
        header = model.headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
        header_text = str(header) if header is not None else ""
    return {
        "available": True,
        "model_class": type(model).__name__,
        "source": "model.data(ToolTipRole)",
        "row_count": row_count,
        "display_length": len(display_text),
        "tooltip_length": len(tooltip_text),
        "full_cell_text_available": complete,
        "header_applicable": header_applicable,
        "header_tooltip_length": len(header_text),
        "full_header_available": header_text == LONG_HEADER_TEXT,
    }


def _visible_rows_helper_metrics(view: QWidget) -> dict[str, Any]:
    """Report the live layout helper controller state without changing the view."""

    controller = getattr(view, "_layout_helpers_visible_rows_controller", None)
    metrics: dict[str, Any] = {
        "attached": controller is not None,
        "controller_class": type(controller).__name__ if controller is not None else None,
        "minimum_height": int(view.minimumHeight()),
        "actual_height": int(view.height()),
        "viewport_height": int(view.viewport().height()) if hasattr(view, "viewport") else None,
    }
    if controller is None:
        return metrics
    for name in ("_rows", "_scheduled", "_base_minimum_height"):
        try:
            value = getattr(controller, name)
        except (AttributeError, RuntimeError):
            continue
        if isinstance(value, (int, bool, str)) or value is None:
            metrics[name.lstrip("_")] = value
    required_height = getattr(controller, "_required_height", None)
    if callable(required_height):
        try:
            metrics["required_height"] = int(required_height())
        except (RuntimeError, TypeError, ValueError) as exc:
            metrics["required_height_error"] = f"{type(exc).__name__}: {exc}"
    return metrics


def _item_view_rows_metrics(view: QWidget, row_count: int) -> dict[str, Any]:
    """Capture actual first-five item geometry alongside the size-hint estimate."""

    from PySide6.QtWidgets import QAbstractItemView, QListView

    if not isinstance(view, QAbstractItemView):
        return {"available": False, "reason": "not_an_item_view"}
    model = view.model()
    if model is None:
        return {"available": False, "reason": "no_model", "row_count": row_count}
    old_scroll = int(view.verticalScrollBar().value())
    try:
        if isinstance(view, QListView):
            view.doItemsLayout()
        view.verticalScrollBar().setValue(0)
        rows: list[dict[str, Any]] = []
        visible_count = 0
        for row in range(min(5, max(0, row_count))):
            try:
                hint = int(view.sizeHintForRow(row))
            except (RuntimeError, TypeError, ValueError):
                hint = -1
            index = model.index(row, 0, view.rootIndex())
            rect = view.visualRect(index) if index.isValid() else None
            viewport_height = int(view.viewport().height())
            complete = bool(
                rect is not None
                and rect.isValid()
                and rect.top() >= 0
                and rect.bottom() < viewport_height
            )
            if complete:
                visible_count += 1
            rows.append(
                {
                    "row": row,
                    "size_hint_height": hint,
                    "visual_rect": _rect_metrics(rect),
                    "fully_visible_at_top": complete,
                }
            )
        return {
            "row_count": row_count,
            "viewport_height": int(view.viewport().height()),
            "first_five_fully_visible_count": visible_count,
            "first_five_all_fully_visible": len(rows) >= 5 and visible_count == 5,
            "rows": rows,
        }
    finally:
        view.verticalScrollBar().setValue(old_scroll)


def _check_native_list_rows(
    view: QWidget,
    entry: dict[str, Any],
    evidence: dict[str, Any],
    geometry_evidence: dict[str, Any],
    workspace_key: str,
    page_path: str,
) -> None:
    from PySide6.QtWidgets import QAbstractItemView

    if not isinstance(view, QAbstractItemView):
        return
    model = view.model()
    row_count = _model_count(model, "rowCount")
    old_scroll = int(view.verticalScrollBar().value())
    first_five_visible = True
    if row_count >= 5:
        for row in range(5):
            rect = view.visualRect(model.index(row, 0))
            if not rect.isValid() or rect.top() < 0 or rect.bottom() >= view.viewport().height():
                first_five_visible = False
                break
    maximum = int(view.verticalScrollBar().maximum())
    if row_count:
        last_index = model.index(row_count - 1, 0)
        view.scrollTo(last_index, QAbstractItemView.ScrollHint.PositionAtBottom)
    view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
    last_rect = view.visualRect(model.index(row_count - 1, 0)) if row_count else None
    last_reachable = bool(
        last_rect is not None
        and last_rect.isValid()
        and last_rect.bottom() >= 0
        and last_rect.top() < view.viewport().height()
    )
    view.verticalScrollBar().setValue(old_scroll)
    if row_count >= 5 and not first_five_visible:
        _add_error(
            evidence,
            geometry_evidence,
            code="native_navigation_fifth_item_not_visible",
            message="保留原始路由清單後，第五個實際選項未完整顯示",
            workspace=workspace_key,
            page=page_path,
            widget=view.objectName() or type(view).__name__,
        )
    entry["fixture_stress"] = {
        "skipped": True,
        "reason": "保留原始功能導航清單，避免改變子頁路由",
        "existing_row_count": row_count,
        "first_five_native_items_visible": first_five_visible,
        "vertical_scroll_maximum": maximum,
        "all_native_items_fit_without_scroll": maximum == 0,
        "last_native_item_reachable": last_reachable,
    }


def _audit_page_scroll_areas(
    page: QWidget,
    page_path: str,
    workspace_key: str,
    page_entry: dict[str, Any],
    evidence: dict[str, Any],
    geometry_evidence: dict[str, Any],
    app: QApplication,
) -> None:
    from PySide6.QtWidgets import QScrollArea

    areas = []
    if isinstance(page, QScrollArea):
        areas.append(page)
    areas.extend(page.findChildren(QScrollArea))
    seen: set[int] = set()
    for area in areas:
        if id(area) in seen or not area.isVisible() or area.isWindow():
            continue
        seen.add(id(area))
        vbar = area.verticalScrollBar()
        hbar = area.horizontalScrollBar()
        vertical_maximum = int(vbar.maximum())
        horizontal_maximum = int(hbar.maximum())
        old_v = int(vbar.value())
        old_h = int(hbar.value())
        vbar.setValue(vertical_maximum)
        hbar.setValue(horizontal_maximum)
        app.processEvents()
        v_reached = int(vbar.value()) == vertical_maximum
        h_reached = int(hbar.value()) == horizontal_maximum
        entry = {
            "object_name": area.objectName(),
            "widget_class": type(area.widget()).__name__ if area.widget() is not None else None,
            "viewport_size_logical": {"width": area.viewport().width(), "height": area.viewport().height()},
            "content_size_logical": (
                {"width": area.widget().width(), "height": area.widget().height()}
                if area.widget() is not None
                else None
            ),
            "vertical_scroll_policy": _scroll_policy_name(area.verticalScrollBarPolicy()),
            "horizontal_scroll_policy": _scroll_policy_name(area.horizontalScrollBarPolicy()),
            "vertical_scroll_maximum": vertical_maximum,
            "horizontal_scroll_maximum": horizontal_maximum,
            "vertical_bottom_reached": v_reached,
            "horizontal_right_reached": h_reached,
            "widget_resizable": bool(area.widgetResizable()),
        }
        page_entry["scroll_areas"].append(entry)
        if vertical_maximum > 0 and not v_reached:
            _add_error(
                evidence,
                geometry_evidence,
                code="outer_scroll_bottom_unreachable",
                message="外層 QScrollArea 垂直捲動條無法到達內容底部",
                workspace=workspace_key,
                page=page_path,
                widget=area.objectName() or "QScrollArea",
            )
        if vertical_maximum > 0 and entry["vertical_scroll_policy"] == "AlwaysOff":
            _add_error(
                evidence,
                geometry_evidence,
                code="outer_vertical_scrollbar_hidden",
                message="外層 QScrollArea 有超出內容，但垂直 scrollbar policy 為 AlwaysOff",
                workspace=workspace_key,
                page=page_path,
                widget=area.objectName() or "QScrollArea",
            )
        if horizontal_maximum > 0 and entry["horizontal_scroll_policy"] == "AlwaysOff":
            _add_error(
                evidence,
                geometry_evidence,
                code="outer_horizontal_scrollbar_hidden",
                message="外層 QScrollArea 有超出內容，但水平 scrollbar policy 為 AlwaysOff",
                workspace=workspace_key,
                page=page_path,
                widget=area.objectName() or "QScrollArea",
            )
        entry["previous_scroll_values"] = {"vertical": old_v, "horizontal": old_h}
        vbar.setValue(old_v)
        hbar.setValue(old_h)
        app.processEvents()


def _capture_workspace_scrollbottom(
    *,
    workspace: QWidget,
    window: QWidget,
    app: QApplication,
    geometry_dir: Path,
    workspace_key: str,
    geometry_key: str,
    evidence: dict[str, Any],
    geometry_evidence: dict[str, Any],
    workspace_evidence: dict[str, Any],
) -> None:
    from PySide6.QtWidgets import QScrollArea

    areas = [area for area in workspace.findChildren(QScrollArea) if area.isVisible() and not area.isWindow()]
    areas.sort(key=lambda area: (int(area.verticalScrollBar().maximum()), int(area.horizontalScrollBar().maximum())), reverse=True)
    for area in areas:
        area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
        area.horizontalScrollBar().setValue(area.horizontalScrollBar().maximum())
    app.processEvents()
    max_vertical = max((int(area.verticalScrollBar().maximum()) for area in areas), default=0)
    if max_vertical <= 0:
        return
    screenshot_path = geometry_dir / f"{workspace_key}_scrollbottom.png"
    if _capture_widget(window, screenshot_path):
        record = {
            "path": str(screenshot_path),
            "scrolled_area_names": [area.objectName() for area in areas if area.verticalScrollBar().maximum() > 0],
            "all_visible_scroll_areas_at_bottom": all(
                area.verticalScrollBar().value() == area.verticalScrollBar().maximum()
                for area in areas
                if area.verticalScrollBar().maximum() > 0
            ),
            "geometry_key": geometry_key,
        }
        workspace_evidence["scrollbottom_screenshots"].append(record)
        evidence["screenshots"].append(str(screenshot_path))
    for area in areas:
        area.verticalScrollBar().setValue(0)
        area.horizontalScrollBar().setValue(0)
    app.processEvents()


def _audit_page_text_controls(
    page: QWidget,
    page_path: str,
    workspace_key: str,
    page_entry: dict[str, Any],
    evidence: dict[str, Any],
    geometry_evidence: dict[str, Any],
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import (
        QAbstractButton,
        QComboBox,
        QGroupBox,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QTextBrowser,
        QTextEdit,
        QWidget,
    )

    all_widgets = [page, *page.findChildren(QWidget)]
    for widget in all_widgets:
        if not widget.isVisible() or widget.isWindow():
            continue
        if not isinstance(
            widget,
            (QLabel, QAbstractButton, QComboBox, QLineEdit, QGroupBox, QPlainTextEdit, QTextEdit, QTextBrowser),
        ):
            continue
        text = ""
        if isinstance(widget, QLabel):
            text = widget.text()
        elif isinstance(widget, QAbstractButton):
            text = widget.text()
        elif isinstance(widget, QComboBox):
            text = widget.currentText()
        elif isinstance(widget, QLineEdit):
            text = widget.text() or widget.placeholderText()
        elif isinstance(widget, QGroupBox):
            text = widget.title()
        elif isinstance(widget, (QPlainTextEdit, QTextEdit, QTextBrowser)):
            text = widget.toPlainText()
        width, height = int(widget.width()), int(widget.height())
        hint = widget.sizeHint()
        metric: dict[str, Any] = {
            "object_name": widget.objectName(),
            "class": type(widget).__name__,
            "text_length": len(text),
            "text_preview": text.replace("\n", " ")[:96],
            "geometry_logical": {"width": width, "height": height},
            "size_hint_logical": {"width": int(hint.width()), "height": int(hint.height())},
            "tooltip_length": len(widget.toolTip() or ""),
        }
        if isinstance(widget, QLabel):
            wrapped = bool(widget.wordWrap())
            hfw = int(widget.heightForWidth(max(width, 1))) if wrapped else -1
            metric["word_wrap"] = wrapped
            metric["height_for_width"] = hfw
            metric["text_format"] = widget.textFormat().value
            if wrapped and hfw >= 0 and height + 2 < hfw:
                _add_error(
                    evidence,
                    geometry_evidence,
                    code="wrapped_label_vertical_clip",
                    message=f"自動換行 QLabel 高度 {height}px 小於目前寬度所需 {hfw}px",
                    workspace=workspace_key,
                    page=page_path,
                    widget=widget.objectName() or "QLabel",
                )
            if len(text) >= 48 and not wrapped:
                is_rich = (
                    widget.textFormat()
                    in (Qt.TextFormat.AutoText, Qt.TextFormat.RichText)
                    and bool(re.search(r"<\s*[A-Za-z][^>]*>", text))
                )
                if is_rich:
                    # QLabel's own sizeHint applies inline CSS font sizes and
                    # weights; measuring stripped markup in the parent font
                    # overstates rich labels and can hide real narrow clipping.
                    text_width = int(widget.sizeHint().width())
                    metric["width_measurement_method"] = "QLabel.sizeHint.rich_text"
                else:
                    text_width = QFontMetrics(widget.font()).horizontalAdvance(
                        _plain_visible_text(text)
                    )
                    metric["width_measurement_method"] = "QFontMetrics.plain_text"
                metric["estimated_text_width"] = int(text_width)
                metric["estimated_horizontal_overflow"] = text_width > width
                tooltip_has_full_text = len(widget.toolTip() or "") >= len(text) or text in (widget.toolTip() or "")
                if text_width > width and not tooltip_has_full_text:
                    _add_error(
                        evidence,
                        geometry_evidence,
                        code="long_label_clipped_without_wrap_or_tooltip",
                        message=f"{len(text)} 字 QLabel 不換行且內容寬 {text_width}px 超過 widget 寬 {width}px",
                        workspace=workspace_key,
                        page=page_path,
                        widget=widget.objectName() or "QLabel",
                    )
        elif isinstance(widget, (QLineEdit, QAbstractButton, QComboBox)):
            metric["vertical_size_sufficient"] = height + 2 >= int(hint.height())
            if height + 2 < int(hint.height()):
                _add_error(
                    evidence,
                    geometry_evidence,
                    code="control_vertical_clip",
                    message=(
                        f"{type(widget).__name__} 高度 {height}px 小於 sizeHint "
                        f"{hint.height()}px"
                    ),
                    workspace=workspace_key,
                    page=page_path,
                    widget=widget.objectName() or type(widget).__name__,
                )
            if isinstance(widget, QAbstractButton) and len(text) >= 32:
                needed = QFontMetrics(widget.font()).horizontalAdvance(_plain_visible_text(text))
                metric["estimated_text_width"] = int(needed)
                metric["estimated_horizontal_overflow"] = needed > width
                if needed > width and len(widget.toolTip() or "") < len(text):
                    _add_error(
                        evidence,
                        geometry_evidence,
                        code="long_button_label_clipped",
                        message=f"長按鈕文字約需 {needed}px，實際寬度 {width}px 且 tooltip 不含全文",
                        workspace=workspace_key,
                        page=page_path,
                        widget=widget.objectName() or type(widget).__name__,
                    )
        elif isinstance(widget, QGroupBox):
            # QGroupBox.sizeHint() includes the entire contents and is expected
            # to exceed its allocated height inside a scrollable page. Check
            # the title line and the actual child bounds instead of comparing
            # the box against its whole-content sizeHint.
            title_height = QFontMetrics(widget.font()).height()
            contents = widget.contentsRect()
            visible_children = [
                child
                for child in widget.findChildren(QWidget)
                if child.isVisible() and child.parentWidget() is widget
            ]
            child_bounds = [
                {
                    "object_name": child.objectName(),
                    "rect": _rect_metrics(child.geometry()),
                    "within_contents": bool(
                        child.geometry().left() >= 0
                        and child.geometry().top() >= 0
                        and child.geometry().right() < widget.width()
                        and child.geometry().bottom() < widget.height()
                    ),
                }
                for child in visible_children
            ]
            metric["title_line_height"] = title_height
            metric["contents_rect"] = _rect_metrics(contents)
            metric["layout_minimum_size"] = (
                {
                    "width": int(widget.layout().minimumSize().width()),
                    "height": int(widget.layout().minimumSize().height()),
                }
                if widget.layout() is not None
                else None
            )
            metric["visible_direct_child_bounds"] = child_bounds
            if any(not child["within_contents"] for child in child_bounds):
                _add_error(
                    evidence,
                    geometry_evidence,
                    code="groupbox_child_outside_contents",
                    message="QGroupBox 內可見直接子控制項超出 group box 內容範圍",
                    workspace=workspace_key,
                    page=page_path,
                    widget=widget.objectName() or "QGroupBox",
                )
        elif isinstance(widget, (QPlainTextEdit, QTextEdit, QTextBrowser)):
            metric["vertical_scroll_maximum"] = int(widget.verticalScrollBar().maximum())
            metric["horizontal_scroll_maximum"] = int(widget.horizontalScrollBar().maximum())
        page_entry["text_controls"].append(metric)


def _plain_visible_text(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _model_count(model: Any, method: str) -> int:
    if model is None:
        return 0
    fn = getattr(model, method, None)
    if not callable(fn):
        return 0
    try:
        from PySide6.QtCore import QModelIndex

        return int(fn(QModelIndex()))
    except TypeError:
        try:
            return int(fn())
        except TypeError:
            return 0


def _scroll_policy_name(policy: Any) -> str:
    from PySide6.QtCore import Qt

    return {
        Qt.ScrollBarPolicy.ScrollBarAsNeeded: "AsNeeded",
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff: "AlwaysOff",
        Qt.ScrollBarPolicy.ScrollBarAlwaysOn: "AlwaysOn",
    }.get(policy, str(policy))


def _wait_layout(widget: QWidget) -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    widget.ensurePolished()
    layout = widget.layout()
    if layout is not None:
        layout.activate()
    QApplication.processEvents()


def _add_error(
    evidence: dict[str, Any],
    geometry_evidence: dict[str, Any],
    *,
    code: str,
    message: str,
    workspace: str | None,
    page: str | None,
    widget: str | None,
) -> None:
    error = _finding("fail", code, message, workspace, page, widget)
    evidence.setdefault("errors", []).append(error)
    geometry_evidence.setdefault("errors", []).append(error)
    if workspace:
        for workspace_result in geometry_evidence.get("workspaces", []):
            if workspace_result.get("key") == workspace:
                workspace_result.setdefault("errors", []).append(error)
                if page:
                    for page_result in workspace_result.get("pages", []):
                        if page_result.get("path") == page:
                            page_result.setdefault("errors", []).append(error)


def _finding(
    severity: str,
    code: str,
    message: str,
    workspace: str | None,
    page: str | None,
    widget: str | None,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "workspace": workspace,
        "page": page,
        "widget": widget,
    }


def _capture_widget(widget: QWidget, path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    pixmap = widget.grab()
    return not pixmap.isNull() and pixmap.save(str(path))


def _rect_metrics(rect: Any) -> dict[str, int] | None:
    if rect is None:
        return None
    try:
        return {
            "x": int(rect.x()),
            "y": int(rect.y()),
            "width": int(rect.width()),
            "height": int(rect.height()),
            "left": int(rect.left()),
            "top": int(rect.top()),
            "right": int(rect.right()),
            "bottom": int(rect.bottom()),
        }
    except (AttributeError, RuntimeError):
        return None


def _workspace_label(window: QWidget, key: str) -> str:
    nav = getattr(window, "left_navigation", None)
    if nav is not None:
        label = nav.label_for_key(key)
        if label:
            return str(label)
    return key


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    return slug[:120] or "page"


def _isolated_file_inventory(root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = -1
        result.append({"path": str(path), "size_bytes": size})
    return result


def _checkpoint_evidence(
    output_dir: Path,
    evidence: dict[str, Any],
    *,
    force: bool = False,
) -> None:
    now = time.monotonic()
    key = str(output_dir.resolve())
    last = _CHECKPOINT_LAST_WRITTEN.get(key, 0.0)
    if not force and last and now - last < 8.0:
        return
    evidence["status"] = "running"
    _write_json_atomic(output_dir / "evidence.partial.json", evidence)
    _write_markdown(output_dir / "report.partial.md", [evidence], complete=False)
    _CHECKPOINT_LAST_WRITTEN[key] = now


def _append_run_event(output_dir: Path, event: str, **details: Any) -> None:
    """Persist a compact progress marker so long page audits are diagnosable."""

    output_dir.mkdir(parents=True, exist_ok=True)
    record = {"time_unix": time.time(), "event": event, **details}
    with (output_dir / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        stream.flush()


def _write_evidence(output_dir: Path, evidence: dict[str, Any], *, partial: bool) -> None:
    name = "evidence.partial.json" if partial else "evidence.json"
    report_name = "report.partial.md" if partial else "report.md"
    _write_json_atomic(output_dir / name, evidence)
    _write_markdown(output_dir / report_name, [evidence], complete=not partial)


def _write_summary(output_dir: Path, results: list[dict[str, Any]], *, complete: bool) -> None:
    errors = [error for result in results for error in result.get("errors", [])]
    gaps = [gap for result in results for gap in result.get("coverage_gaps", [])]
    summary = {
        "status": (
            "failed"
            if errors
            or gaps
            or any(result.get("status") == "failed" for result in results)
            else ("passed" if complete else "running")
        ),
        "evidence_kind": "offscreen_real_mainwindow_geometry",
        "complete": complete,
        "scales": results,
        "error_count": len(errors),
        "coverage_gap_count": len(gaps),
    }
    _write_json_atomic(output_dir / "summary.json", summary)
    _write_markdown(output_dir / "report.md", results, complete=complete)


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _write_markdown(path: Path, results: list[dict[str, Any]], *, complete: bool) -> None:
    lines = [
        "# MainWindow 全工作區版面稽核",
        "",
        f"狀態：**{'完整' if complete else '執行中，資料會逐頁更新'}**",
        "",
        "此報告使用真實 `MainWindow` 與正式 theme。資料表版面壓力測試替換為短暫合成資料並還原原 model；所有來源根目錄與設定路徑都隔離於 ignored QA output。runner 不觸發更新、推薦、回測或保存操作。",
        "",
        "`actual_max` 是 2293×912 logical client 尺寸的 offscreen 模擬；它沒有量測 Windows 原生視窗框。scale factor 由獨立 child process 於 Qt 啟動前設定。",
        "",
        "## 執行摘要",
        "",
        "| scale | 狀態 | 幾何組數 | 工作區組數 | 子頁組數 | 失敗 | coverage gap |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        geometries = result.get("geometry_runs", [])
        pages = [
            page
            for geometry in geometries
            for workspace in geometry.get("workspaces", [])
            for page in workspace.get("pages", [])
        ]
        pages.extend(
            page
            for geometry in geometries
            for workspace in geometry.get("workspaces", [])
            for scenario in workspace.get("scenarios", [])
            for page in scenario.get("pages", [])
        )
        lines.append(
            "| {scale} | {status} | {geometry_count} | {workspace_count} | {page_count} | {errors} | {gaps} |".format(
                scale=result.get("scale_factor_requested", "?"),
                status=result.get("status", "running"),
                geometry_count=len(geometries),
                workspace_count=sum(len(geometry.get("workspaces", [])) for geometry in geometries),
                page_count=len(pages),
                errors=len(result.get("errors", [])),
                gaps=len(result.get("coverage_gaps", [])),
            )
        )
    lines.extend(["", "## Failures", ""])
    all_errors = [
        (result.get("scale_factor_requested"), error)
        for result in results
        for error in result.get("errors", [])
    ]
    if not all_errors:
        lines.append("目前沒有已記錄的幾何失敗。" if complete else "尚未產生失敗記錄。")
    else:
        for scale, error in all_errors:
            lines.append(
                f"- **{error.get('code')}** (scale {scale}, {error.get('workspace') or 'shell'} / {error.get('page') or '—'}): {error.get('message')}"
            )
    lines.extend(["", "## Coverage gaps", ""])
    all_gaps = [
        (result.get("scale_factor_requested"), gap)
        for result in results
        for gap in result.get("coverage_gaps", [])
    ]
    if not all_gaps:
        lines.append("沒有未處理的資料元件 coverage gap。" if complete else "尚未產生 coverage gap 記錄。")
    else:
        for scale, gap in all_gaps:
            lines.append(
                f"- **{gap.get('code')}** (scale {scale}, {gap.get('workspace') or '—'} / {gap.get('page') or '—'}): {gap.get('message')}"
            )
    for result in results:
        lines.extend(
            [
                "",
                f"## Scale {result.get('scale_factor_requested', '?')} — 工作區 / 子頁 inventory",
                "",
                f"theme font：{result.get('theme_font', '未知')}；CJK glyph：{result.get('theme_cjk_glyph_available', '未知')}。",
                "",
            ]
        )
        for geometry in result.get("geometry_runs", []):
            size = geometry.get("requested_size_logical", {})
            observed_size = geometry.get("observed_main_window_size_logical", {})
            shell = geometry.get("shell", {})
            lines.extend(
                [
                    f"### {geometry.get('label', geometry.get('key'))} — {size.get('width')}×{size.get('height')}",
                    "",
                    (
                        "MainWindow client："
                        f"{observed_size.get('width', '?')}×{observed_size.get('height', '?')}；"
                        f"左側導覽 {shell.get('left_navigation', {}).get('width', '?')}px；"
                        f"導覽符合中央區域={shell.get('navigation_fits_central', '未知')}；"
                        f"工作區符合中央區域={shell.get('workspace_fits_central', '未知')}。"
                    ),
                    "",
                    "| 工作區 | 可見 | 子頁 | tables/lists | scroll areas | 截圖 |",
                    "|---|---:|---:|---:|---:|---|",
                ]
            )
            for workspace in geometry.get("workspaces", []):
                all_pages = list(workspace.get("pages", []))
                all_pages.extend(
                    page
                    for scenario in workspace.get("scenarios", [])
                    for page in scenario.get("pages", [])
                )
                page_names = [page.get("path", "") for page in all_pages]
                view_count = sum(len(page.get("tables_and_lists", [])) for page in all_pages)
                scroll_count = sum(len(page.get("scroll_areas", [])) for page in all_pages)
                screenshot = workspace.get("screenshot") or "—"
                lines.append(
                    f"| {workspace.get('label')} (`{workspace.get('key')}`) | {workspace.get('visible')} | {len(page_names)} | {view_count} | {scroll_count} | `{screenshot}` |"
                )
                for page_name in page_names:
                    lines.append(f"| ↳ `{page_name}` |  |  |  |  |  |")
                for record in workspace.get("scrollbottom_screenshots", []):
                    lines.append(f"| ↳ bottom screenshot |  |  |  |  | `{record.get('path')}` |")
                lines.extend(["", f"#### {workspace.get('label')} 詳細幾何", ""])
                for page in workspace.get("pages", []):
                    _append_page_geometry_report(lines, page, title_prefix="基準頁")
                for scenario in workspace.get("scenarios", []):
                    lines.extend(
                        [
                            f"##### 情境：{scenario.get('label', scenario.get('key'))}",
                            "",
                            scenario.get("description", ""),
                            "",
                            "切頁後 MainWindow 尺寸不變："
                            f"{scenario.get('main_window_size_unchanged', '未知')}。",
                        ]
                    )
                    for page in scenario.get("pages", []):
                        _append_page_geometry_report(lines, page, title_prefix="情境頁")
                    focus_screenshot = scenario.get("focus_screenshot")
                    if isinstance(focus_screenshot, dict) and focus_screenshot.get("path"):
                        lines.append(
                            "- 情境目標捲動截圖："
                            f"{focus_screenshot['path']}；target viewport="
                            f"{focus_screenshot.get('target_rect_in_viewport')}；"
                            f"scroll={focus_screenshot.get('vertical_scroll_value')}/"
                            f"{focus_screenshot.get('vertical_scroll_maximum')}。"
                        )
                    for error in scenario.get("errors", []):
                        lines.append(f"- 失敗 {error.get('code')}：{error.get('message')}")
                    for gap in scenario.get("coverage_gaps", []):
                        lines.append(f"- Coverage gap {gap.get('code')}：{gap.get('message')}")
                    lines.append("")
            lines.append("")
            if geometry.get("errors"):
                lines.append("本尺寸錯誤：")
                lines.extend(
                    f"- `{item.get('code')}`: {item.get('message')}"
                    for item in geometry["errors"]
                )
                lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_page_geometry_report(
    lines: list[str], page: dict[str, Any], *, title_prefix: str
) -> None:
    """Append a per-page inventory backed by captured widget geometry."""

    rect = page.get("geometry_logical", {})
    tables = page.get("tables_and_lists", [])
    scroll_areas = page.get("scroll_areas", [])
    controls = page.get("text_controls", [])
    long_controls = [control for control in controls if control.get("text_length", 0) >= 48]
    clipped_controls = [
        control
        for control in controls
        if control.get("vertical_size_sufficient") is False
        or control.get("estimated_horizontal_overflow") is True
        or (
            control.get("class") == "QLabel"
            and control.get("word_wrap")
            and control.get("height_for_width", -1) >= 0
            and control.get("geometry_logical", {}).get("height", 0)
            + 2
            < control.get("height_for_width", -1)
        )
    ]
    lines.extend(
        [
            f"###### {title_prefix}：{page.get('path', '?')} — {page.get('widget_class', '?')}",
            "",
            (
                f"可見={page.get('visible', '未知')}；頁面尺寸="
                f"{rect.get('width', '?')}×{rect.get('height', '?')}；"
                f"item views={len(tables)}；scroll areas={len(scroll_areas)}；"
                f"文字／控制項={len(controls)}（長內容≥48字：{len(long_controls)}；"
                f"量測可疑／不足：{len(clipped_controls)}）。"
            ),
        ]
    )
    if page.get("screenshot"):
        lines.append(f"- 初始資料截圖：{page['screenshot']}")
    if page.get("fixture_screenshot"):
        lines.append(f"- 合成資料截圖（表格前五列）：{page['fixture_screenshot']}")
    for error in page.get("errors", []):
        lines.append(f"- 失敗 {error.get('code')}：{error.get('message')}")
    for gap in page.get("coverage_gaps", []):
        lines.append(f"- Coverage gap {gap.get('code')}：{gap.get('message')}")

    for index, view in enumerate(tables, start=1):
        baseline = view.get("baseline_model", {})
        first_five = view.get("first_five_rows", {})
        stress = view.get("fixture_stress") or {}
        helper = stress.get("visible_rows_helper") or view.get("visible_rows_helper") or {}
        stress_rows = stress.get("first_five_rows", {})
        horizontal = stress.get("horizontal_scroll") or {}
        tooltip = stress.get("tooltip") or {}
        if stress.get("skipped"):
            stress_summary = f"壓力資料未替換：{stress.get('reason', '未提供原因')}"
        else:
            restoration = stress.get("restoration") or view.get("fixture_restoration") or {}
            stress_summary = (
                f"合成 {stress.get('rows', '?')}×{stress.get('columns', '?')}；"
                f"viewport={stress.get('viewport_size_logical', {}).get('width', '?')}×"
                f"{stress.get('viewport_size_logical', {}).get('height', '?')}；"
                f"第5列完整可見={stress.get('fifth_row_fully_visible', '未知')}；"
                f"前5列完整數={stress_rows.get('first_five_fully_visible_count', '?')}；"
                f"最後一列可達={stress.get('lower_row_reachable', '未知')}；"
                f"垂直 range={stress.get('vertical_scroll_maximum', '?')}"
            )
            if horizontal.get("applicable"):
                stress_summary += (
                    f"；水平 policy={horizontal.get('horizontal_scroll_policy', '?')}；"
                    f"水平 range={horizontal.get('scroll_range_maximum', '?')}；"
                    f"最右欄可達={horizontal.get('last_column_reachable', '未知')}"
                )
            if tooltip:
                stress_summary += (
                    f"；長 cell tooltip 全文={tooltip.get('full_cell_text_available', '未知')}"
                )
            if restoration:
                failed_restores = ",".join(restoration.get("failed_checks", [])) or "無"
                stress_summary += (
                    f"；fixture還原完整={restoration.get('passed', '未知')}"
                    f"；還原失敗檢查={failed_restores}"
                )
            width_restore = stress.get("column_width_restore") or {}
            if width_restore:
                stress_summary += (
                    f"；欄寬viewport baseline/fixture/restored="
                    f"{width_restore.get('baseline_viewport_width', '?')}/"
                    f"{width_restore.get('fixture_viewport_width_before_restore', '?')}/"
                    f"{width_restore.get('restored_viewport_width', '?')}px；"
                    f"resize modes restored={width_restore.get('resize_modes_restored', '未知')}；"
                    f"固定={width_restore.get('fixed_widths_passed', '未知')}；"
                    f"自然寬={width_restore.get('natural_widths_passed', '未知')}；"
                    f"stretch allocation={width_restore.get('viewport_allocation_passed', '未知')}"
                )
            header_restore = stress.get("horizontal_header_state_readback") or {}
            if header_restore:
                contract = header_restore.get("semantic_contract") or {}
                stress_summary += (
                    f"；header契約還原={contract.get('passed', '未知')}；"
                    f"restoreState接受={header_restore.get('restore_state_accepted', '未知')}；"
                    f"序列化bytes相同={header_restore.get('serialized_equal', '未知')}；"
                    f"bytes差異由自適應欄寬解釋="
                    f"{header_restore.get('serialization_difference_explained_by_adaptive_width', '未知')}"
                )
            baseline_settle = stress.get("baseline_header_settle") or {}
            if baseline_settle:
                stress_summary += (
                    f"；baseline mode-aware settle Fixed/Interactive原寬保留="
                    f"{baseline_settle.get('fixed_interactive_widths_preserved', '未知')}；"
                    f"前/後欄寬={baseline_settle.get('before_widths', '?')}/"
                    f"{baseline_settle.get('after_widths', '?')}"
                )
        lines.append(
            f"- Item view {index}: {view.get('object_name') or view.get('class')} "
            f"({view.get('class', '?')})；baseline {baseline.get('rows', '?')}×"
            f"{baseline.get('columns', '?')}，viewport="
            f"{view.get('viewport_size_logical', {}).get('width', '?')}×"
            f"{view.get('viewport_size_logical', {}).get('height', '?')}，"
            f"baseline 前5列完整數={first_five.get('first_five_fully_visible_count', '?')}；"
            f"helper attached={helper.get('attached', '未知')}，"
            f"minimum/required height={helper.get('minimum_height', '?')}/"
            f"{helper.get('required_height', '?')}。{stress_summary}。"
        )
    for index, area in enumerate(scroll_areas, start=1):
        viewport = area.get("viewport_size_logical", {})
        content = area.get("content_size_logical") or {}
        lines.append(
            f"- Scroll area {index}: {area.get('object_name') or area.get('widget_class')}；"
            f"viewport={viewport.get('width', '?')}×{viewport.get('height', '?')}，"
            f"content={content.get('width', '?')}×{content.get('height', '?')}；"
            f"vertical policy/range/bottom={area.get('vertical_scroll_policy', '?')}/"
            f"{area.get('vertical_scroll_maximum', '?')}/"
            f"{area.get('vertical_bottom_reached', '未知')}；horizontal policy/range/right="
            f"{area.get('horizontal_scroll_policy', '?')}/"
            f"{area.get('horizontal_scroll_maximum', '?')}/"
            f"{area.get('horizontal_right_reached', '未知')}。"
        )
    report_controls = clipped_controls + [
        item for item in long_controls if item not in clipped_controls
    ]
    for control in report_controls:
        details = control.get("geometry_logical", {})
        text = control.get("text_preview", "").replace("|", "\\|")
        lines.append(
            f"- 文字檢視 {control.get('object_name') or control.get('class')}："
            f"{control.get('class')}，{control.get('text_length', 0)} 字，"
            f"尺寸={details.get('width', '?')}×{details.get('height', '?')}，"
            f"wrap={control.get('word_wrap', '—')}，"
            f"提示全文={control.get('tooltip_length', 0)} 字，"
            f"寬度量測={control.get('width_measurement_method', '—')}；"
            f"文字預覽：{text}"
        )
    lines.append("")


def _timeout_result(scale: str, scale_dir: Path, exc: subprocess.TimeoutExpired) -> dict[str, Any]:
    partial = scale_dir / "evidence.partial.json"
    if partial.exists():
        result = json.loads(partial.read_text(encoding="utf-8"))
    else:
        result = {"geometry_runs": [], "coverage_gaps": []}
    result["status"] = "failed"
    result.setdefault("errors", []).append(
        {
            "severity": "fail",
            "code": "runner_timeout",
            "message": f"scale {scale} runner 超過 900 秒：{exc}",
        }
    )
    return result


def _format_traceback(exc: BaseException) -> str:
    import traceback

    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


if __name__ == "__main__":
    raise SystemExit(main())
