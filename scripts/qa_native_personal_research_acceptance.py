"""以隔離 QA snapshot 驗證可見 Qt 個人研究 UI 的保存與讀回旅程。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import qa_personal_research_ui as isolated_launcher


QA_ROOT = REPOSITORY_ROOT / "output" / "qa" / "personal_daily_product_20261006"
RUN_ROOT_BASE = QA_ROOT / "personal_research_ui"
LEARNING_ROOT_BASE = QA_ROOT / "personal_research_learning"
PRECHECK_ROOT = QA_ROOT / "native_qt_visible_preflight"
SNAPSHOT_PATH = REPOSITORY_ROOT / isolated_launcher.PINNED_SNAPSHOT_RELATIVE
SNAPSHOT_RECEIPT_PATH = REPOSITORY_ROOT / isolated_launcher.PINNED_SNAPSHOT_RECEIPT_RELATIVE
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
LEGACY_CAPTURE_PROBE_RUN_ID = "native_qt_wp3_20260928_01"
WINDOW_TITLE_PREFIX = "個人研究 QA｜固定快照複本｜可見 Qt 自動化"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_create_only(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _write_json_create_only(path: Path, payload: Any) -> str:
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    _write_create_only(path, content)
    return _sha256_bytes(content)


def _stat_identity(path: Path) -> dict[str, Any]:
    info = path.stat()
    return {
        "path": str(path.resolve(strict=True)),
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "size_bytes": int(info.st_size),
        "mtime_ns": int(info.st_mtime_ns),
        "regular_file": path.is_file(),
    }


def _hash_file(path: Path, *, max_bytes: int = 4 * 1024 * 1024) -> tuple[str, int]:
    info = path.stat()
    if not path.is_file() or info.st_size > max_bytes:
        raise RuntimeError(f"QA 證據檔不存在、非一般檔案或超過上限：{path}")
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise RuntimeError(f"QA 證據檔讀取超過上限：{path}")
            digest.update(chunk)
    if total != info.st_size:
        raise RuntimeError(f"QA 證據檔讀取長度與 stat 不符：{path}")
    return digest.hexdigest(), total


class ScreenCaptureMismatch(RuntimeError):
    """桌面截圖無法證明對應指定 Qt widget 時拒絕落盤。"""

    def __init__(self, message: str, details: dict[str, Any]) -> None:
        super().__init__(message)
        self.details = details


def _compare_pixmap_to_widget(screen_pixmap: Any, widget_pixmap: Any) -> dict[str, Any]:
    """逐像素比對桌面擷取與 Qt widget；差異超出明示容差即拒絕。"""

    import numpy as np
    from PySide6.QtGui import QImage

    screen_image = screen_pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    widget_image = widget_pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    screen_size = (screen_image.width(), screen_image.height())
    widget_size = (widget_image.width(), widget_image.height())
    if screen_size != widget_size or screen_size[0] <= 0 or screen_size[1] <= 0:
        return {
            "matches": False,
            "reason": "pixel_dimensions_differ",
            "screen_size": list(screen_size),
            "widget_size": list(widget_size),
            "sample_count": 0,
            "pixel_count": 0,
            "pixels_over_8_levels": None,
            "mean_abs_channel_delta": None,
            "fraction_within_8_levels": None,
        }

    height, width = screen_size[1], screen_size[0]
    screen_bytes = bytes(screen_image.constBits())
    widget_bytes = bytes(widget_image.constBits())
    expected_size = screen_image.sizeInBytes()
    pixel_count = width * height
    if len(screen_bytes) != expected_size or len(widget_bytes) != expected_size:
        return {
            "matches": False,
            "reason": "pixel_buffer_size_invalid",
            "screen_size": list(screen_size),
            "widget_size": list(widget_size),
            "sample_count": 0,
            "pixel_count": pixel_count,
            "pixels_over_8_levels": None,
            "mean_abs_channel_delta": None,
            "fraction_within_8_levels": None,
        }
    screen_pixels = np.frombuffer(screen_bytes, dtype=np.uint8).reshape(height, width, 4)
    widget_pixels = np.frombuffer(widget_bytes, dtype=np.uint8).reshape(height, width, 4)
    rgb_delta = np.abs(
        screen_pixels[:, :, :3].astype(np.int16)
        - widget_pixels[:, :, :3].astype(np.int16)
    )
    max_delta_by_pixel = rgb_delta.max(axis=2)
    pixels_over_8 = int(np.count_nonzero(max_delta_by_pixel > 8))
    near_equal = pixel_count - pixels_over_8
    mean_delta = float(rgb_delta.mean())
    near_fraction = near_equal / pixel_count
    matches = mean_delta <= 2.0 and pixels_over_8 == 0
    return {
        "matches": matches,
        "reason": "full_image_pixels_match" if matches else "full_image_pixels_differ",
        "screen_size": list(screen_size),
        "widget_size": list(widget_size),
        "sample_count": pixel_count,
        "pixel_count": pixel_count,
        "pixels_over_8_levels": pixels_over_8,
        "mean_abs_channel_delta": mean_delta,
        "fraction_within_8_levels": near_fraction,
        "acceptance": {
            "mean_abs_channel_delta_max": 2.0,
            "fraction_within_8_levels_min": 1.0,
            "comparison_scope": "every_pixel_every_rgb_channel",
        },
    }


def _capture_window(window: Any, label: str, destination: Path) -> dict[str, Any]:
    from PySide6.QtCore import QBuffer, QIODevice

    if not window.isVisible():
        raise RuntimeError(f"視窗未顯示，不能擷取步驟 {label}")
    handle = window.windowHandle()
    if handle is None or not handle.isExposed():
        raise RuntimeError(f"視窗未暴露於桌面，不能擷取步驟 {label}")
    screen = window.screen()
    if screen is None:
        raise RuntimeError(f"視窗沒有對應螢幕，不能擷取步驟 {label}")
    window_id = int(window.winId())
    pixmap = screen.grabWindow(window_id)
    if pixmap.isNull() or pixmap.width() <= 0 or pixmap.height() <= 0:
        raise RuntimeError(f"QScreen.grabWindow 對步驟 {label} 回傳空影像")
    widget_pixmap = window.grab()
    if widget_pixmap.isNull() or widget_pixmap.width() <= 0 or widget_pixmap.height() <= 0:
        raise RuntimeError(f"Qt widget grab 對步驟 {label} 回傳空影像")
    comparison = _compare_pixmap_to_widget(pixmap, widget_pixmap)
    if not comparison["matches"]:
        raise ScreenCaptureMismatch(
            f"QScreen 影像未能核對為目標 Qt widget（{label}）：{comparison}",
            {
                "label": label,
                "window_id": window_id,
                "window_title": window.windowTitle(),
                "comparison": comparison,
                "screen_capture_written": False,
            },
        )
    window_id_after = int(window.winId())
    if window_id_after != window_id:
        raise ScreenCaptureMismatch(
            f"Qt window ID 在擷取期間改變（{label}）",
            {
                "label": label,
                "window_id_before": window_id,
                "window_id_after": window_id_after,
                "window_title": window.windowTitle(),
                "comparison": comparison,
                "screen_capture_written": False,
            },
        )
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("無法建立 Qt 截圖緩衝區")
    if not pixmap.save(buffer, "PNG"):
        buffer.close()
        raise RuntimeError(f"Qt 無法編碼步驟 {label} 截圖")
    image_bytes = bytes(buffer.data())
    buffer.close()
    if len(image_bytes) < 128:
        raise RuntimeError(f"步驟 {label} 截圖資料長度過短")
    _write_create_only(destination, image_bytes)
    return {
        "label": label,
        "path": str(destination.resolve(strict=True)),
        "sha256": _sha256_bytes(image_bytes),
        "size_bytes": len(image_bytes),
        "width": int(pixmap.width()),
        "height": int(pixmap.height()),
        "window_id": window_id,
        "window_title": window.windowTitle(),
        "window_geometry": {
            "x": int(window.x()),
            "y": int(window.y()),
            "width": int(window.width()),
            "height": int(window.height()),
        },
        "screen_name": screen.name(),
        "capture_kind": "QScreen.grabWindow_verified_against_QWidget.grab",
        "screen_matches_widget": True,
        "screen_widget_comparison": comparison,
        "screen_geometry": {
            "x": int(screen.geometry().x()),
            "y": int(screen.geometry().y()),
            "width": int(screen.geometry().width()),
            "height": int(screen.geometry().height()),
        },
    }


def _visible_qt_preflight(run_id: str) -> tuple[dict[str, Any], int]:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

    evidence_dir = PRECHECK_ROOT / run_id
    evidence_dir.mkdir(parents=True, exist_ok=False)
    receipt: dict[str, Any] = {
        "schema_version": "visible-qt-desktop-preflight.v1",
        "attempt_id": run_id,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "可見 Qt 桌面能力前置檢查，不是產品旅程驗收",
        "qt_platform_requested": "windows",
        "main_window_started": False,
        "snapshot_copy_started": False,
        "status": "FAILED",
    }
    screenshot_path = evidence_dir / "visible_qt_preflight.png"
    app: Any = None
    probe: Any = None
    try:
        if os.name != "nt":
            raise RuntimeError("可見 Qt 驗收只支援 Windows；目前不是 Windows")
        os.environ["QT_QPA_PLATFORM"] = "windows"
        os.environ["PYTHONUTF8"] = "1"
        os.environ["PYTHONIOENCODING"] = "utf-8"
        app = QApplication([str(Path(__file__).resolve())])
        app.setOrganizationName("TechnicalAnalysis")
        app.setApplicationName("TechnicalAnalysis")
        platform_name = QGuiApplication.platformName()
        receipt["qt_platform_actual"] = platform_name
        if platform_name.lower() != "windows":
            raise RuntimeError(f"Qt platform 實際值不是 windows：{platform_name}")
        probe = QWidget()
        probe.setWindowTitle(f"{WINDOW_TITLE_PREFIX}｜桌面預檢｜{run_id}")
        probe.resize(560, 220)
        layout = QVBoxLayout(probe)
        layout.addWidget(QLabel("原生視窗顯示／截圖能力檢查；尚未載入產品或複製資料。"))
        probe.show()
        probe.raise_()
        probe.activateWindow()
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            app.processEvents()
            handle = probe.windowHandle()
            if probe.isVisible() and handle is not None and handle.isExposed():
                break
            time.sleep(0.05)
        if not probe.isVisible() or probe.windowHandle() is None or not probe.windowHandle().isExposed():
            raise RuntimeError("Qt 預檢視窗在 8 秒內未暴露於 Windows 桌面")
        captured = _capture_window(probe, "desktop_preflight", screenshot_path)
        receipt.update(
            {
                "status": "PASS",
                "main_window_started": False,
                "snapshot_copy_started": False,
                "screenshot": captured,
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        return receipt, 0
    except Exception as exc:
        receipt.update(
            {
                "status": "NATIVE_DISPLAY_UNAVAILABLE",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "capture_evidence": (
                    exc.details if isinstance(exc, ScreenCaptureMismatch) else None
                ),
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "snapshot_copy_started": False,
            }
        )
        return receipt, 2
    finally:
        if probe is not None:
            probe.close()
        if app is not None:
            app.processEvents()
            app.quit()
        _write_json_create_only(evidence_dir / "preflight_receipt.json", receipt)


def _capture_probe_workspace_paths(run_id: str) -> tuple[Path, Path]:
    """解析 capture-only run ID，拒絕舊工作區與路徑字元。"""

    if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("capture probe run-id 僅接受英數、底線與連字號，長度最多 64")
    if run_id.casefold() == LEGACY_CAPTURE_PROBE_RUN_ID.casefold():
        raise ValueError("capture probe 不可重用既有 legacy _01 工作區；請指定全新 run-id")
    return RUN_ROOT_BASE / run_id, LEARNING_ROOT_BASE / run_id


def _mainwindow_capture_probe(run_id: str) -> int:
    """只顯示指定已備妥的 MainWindow，無業務操作且核對畫面來源。"""

    run_root, learning_output_root = _capture_probe_workspace_paths(run_id)
    layout = isolated_launcher._runtime_layout(run_root)
    attempt_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid4().hex[:8]
    receipt_path = layout.receipts_dir / f"mainwindow_capture_probe_{attempt_id}.json"
    screenshot_path = (
        layout.receipts_dir
        / "screenshots"
        / f"mainwindow_capture_probe_{attempt_id}.png"
    )
    receipt: dict[str, Any] = {
        "schema_version": "native-qt-mainwindow-capture-probe.v1",
        "attempt_id": attempt_id,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "FAILED",
        "classification": "只顯示 MainWindow 並核對擷取來源；沒有業務操作或推薦執行",
        "run_id": run_id,
        "run_root": str(run_root.resolve(strict=False)),
        "learning_output_root": str(learning_output_root.resolve(strict=False)),
        "screenshot_path_if_verified": str(screenshot_path.resolve(strict=False)),
        "screenshot_written": False,
        "copy_started": False,
        "business_actions": 0,
        "recommendation_executed": False,
        "canonical_result_saved": False,
        "formal_data_read_or_written": False,
        "scheduler_registered": False,
        "http_requested": False,
    }
    app: Any = None
    window: Any = None
    environment_before: dict[str, str] | None = None
    before: dict[str, Any] | None = None
    try:
        if os.name != "nt":
            raise RuntimeError("MainWindow capture probe 僅支援 Windows")
        if not run_root.is_dir() or not learning_output_root.is_dir():
            raise RuntimeError("指定 run／learning workspace 不存在；probe 不會建立或複製 workspace")
        verified_layout, manifest, verified = isolated_launcher._verify_prepared_workspace(
            run_root=run_root,
            policy_config_path=layout.policy_config_path,
            learning_output_root=learning_output_root,
        )
        if verified_layout.working_db_path != layout.working_db_path:
            raise RuntimeError("prepared workspace DB path 與 runtime layout 不符")
        if layout.policy_config_path.exists():
            raise RuntimeError("個人政策檔已存在；probe 要求 fresh rule-only 狀態")
        before = {
            "working_db_sha256": manifest["working_copy"]["working_sha256"],
            "working_db_size_bytes": manifest["working_copy"]["working_size_bytes"],
            "working_db_identity": manifest["working_copy"]["working_file_identity"],
            "working_sqlite_scope": verified["working_sqlite_scope"],
            "policy_exists": False,
            "learning_tree_pin": verified["learning_pin"],
        }
        receipt["prepared_workspace_before"] = before
        receipt["isolation_manifest_path"] = str(
            (layout.receipts_dir / "isolation_manifest.json").resolve(strict=True)
        )
        receipt["isolation_manifest_sha256"] = _hash_file(
            layout.receipts_dir / "isolation_manifest.json", max_bytes=4 * 1024 * 1024
        )[0]

        isolated_env = _phase_environment(run_root, learning_output_root)
        environment_before = os.environ.copy()
        os.environ.clear()
        os.environ.update(isolated_env)
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import QApplication

        from ui_qt.main import MainWindow, apply_app_theme

        app = QApplication([str(Path(__file__).resolve()), "--mainwindow-capture-probe"])
        app.setOrganizationName("TechnicalAnalysis")
        app.setApplicationName("TechnicalAnalysis")
        apply_app_theme(app)
        window = MainWindow(policy_config_path=layout.policy_config_path)
        view = getattr(window, "recommendation_view", None)
        policy = getattr(view, "_personal_use_policy", None)
        if getattr(policy, "mode", None) != "rule_only":
            raise RuntimeError("MainWindow 個人政策不是預期的 rule_only")
        if layout.policy_config_path.exists():
            raise RuntimeError("MainWindow 初始化意外建立個人政策檔")
        title = f"{WINDOW_TITLE_PREFIX}｜MainWindow capture probe｜{attempt_id}"
        window.setWindowTitle(title)
        window.resize(1440, 900)
        window.show()
        window.raise_()
        window.activateWindow()
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            app.processEvents()
            handle = window.windowHandle()
            active_window = QApplication.activeWindow()
            if (
                window.isVisible()
                and handle is not None
                and handle.isExposed()
                and active_window is window
            ):
                break
            time.sleep(0.05)
        handle = window.windowHandle()
        if not window.isVisible() or handle is None or not handle.isExposed():
            raise RuntimeError("MainWindow 在 12 秒內未成為 exposed 視窗")
        if QApplication.activeWindow() is not window:
            raise RuntimeError("MainWindow 未成為前景 active window；不擷取桌面畫面")
        receipt["window_evidence"] = {
            "class": type(window).__name__,
            "module": type(window).__module__,
            "title": window.windowTitle(),
            "window_id": int(window.winId()),
            "visible": bool(window.isVisible()),
            "exposed": bool(handle.isExposed()),
            "active_window_is_mainwindow": QApplication.activeWindow() is window,
            "qt_platform": QGuiApplication.platformName(),
            "geometry": {
                "x": int(window.x()),
                "y": int(window.y()),
                "width": int(window.width()),
                "height": int(window.height()),
            },
            "personal_policy_mode": str(getattr(policy, "mode", None)),
        }
        captured = _capture_window(window, "mainwindow_capture_probe", screenshot_path)
        receipt["screenshot"] = captured
        receipt["screenshot_written"] = True
        receipt["status"] = "PASS_CAPTURE_MATCHED"
    except ScreenCaptureMismatch as exc:
        receipt["status"] = "CAPTURE_MISMATCH"
        receipt["capture_failure"] = exc.details
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        receipt["status"] = "PROBE_FAILED"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if window is not None:
            window.close()
            if app is not None:
                app.processEvents()
        if app is not None:
            app.quit()
            app.processEvents()
        if before is not None:
            try:
                _, after_manifest, after_verified = isolated_launcher._verify_prepared_workspace(
                    run_root=run_root,
                    policy_config_path=layout.policy_config_path,
                    learning_output_root=learning_output_root,
                )
                receipt["prepared_workspace_after"] = {
                    "working_db_sha256": after_manifest["working_copy"]["working_sha256"],
                    "working_db_size_bytes": after_manifest["working_copy"]["working_size_bytes"],
                    "working_db_identity": after_manifest["working_copy"]["working_file_identity"],
                    "working_sqlite_scope": after_verified["working_sqlite_scope"],
                    "policy_exists": layout.policy_config_path.exists(),
                    "learning_tree_pin": after_verified["learning_pin"],
                }
                if receipt["prepared_workspace_after"]["policy_exists"]:
                    receipt["status"] = "FAILED_WORKSPACE_MUTATION"
                    receipt["error"] = "capture probe 後意外存在個人政策檔"
                if receipt["prepared_workspace_after"]["working_db_sha256"] != before["working_db_sha256"]:
                    receipt["status"] = "FAILED_WORKSPACE_MUTATION"
                    receipt["error"] = "capture probe 改變了隔離 working DB"
            except Exception as exc:
                receipt["status"] = "FAILED_POSTCHECK"
                receipt["postcheck_error"] = f"{type(exc).__name__}: {exc}"
        if environment_before is not None:
            os.environ.clear()
            os.environ.update(environment_before)
        if not receipt["screenshot_written"] and screenshot_path.exists():
            receipt["status"] = "FAILED_UNEXPECTED_SCREENSHOT"
            receipt["error"] = "未通過比對但 probe 路徑已有 screenshot；不會覆寫或移除"
        receipt["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        receipt["receipt_path"] = str(receipt_path.resolve(strict=False))
        if before is not None:
            receipt["receipt_sha256"] = _write_json_create_only(receipt_path, receipt)
        else:
            receipt["receipt_written"] = False
            receipt["receipt_write_skipped_reason"] = (
                "workspace 在寫入任何 run 內證據前未通過完整 pin 驗證"
            )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["status"] == "PASS_CAPTURE_MATCHED" else 2


def _phase_environment(run_root: Path, learning_root: Path) -> dict[str, str]:
    layout = isolated_launcher._runtime_layout(run_root)
    env = os.environ.copy()
    env.update(
        {
            "DATA_ROOT": str(layout.data_root_base.resolve()),
            "OUTPUT_ROOT": str(layout.output_root_base.resolve()),
            "PROFILE": "test",
            "RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(learning_root.resolve()),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "QT_QPA_PLATFORM": "windows",
        }
    )
    for key in isolated_launcher._ISOLATED_ARTIFACT_ENV:
        env.pop(key, None)
    for key in tuple(env):
        if key.startswith(("FORMAL_DAILY_", "PIT_SECTOR_", "PIT_MEMBERSHIP_")):
            env.pop(key, None)
    env["FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE"] = str(
        run_root / ".missing-formal-runtime-binding.json"
    )
    return env


def _spawn_phase(
    *,
    run_id: str,
    phase: str,
    run_root: Path,
    learning_root: Path,
    timeout_seconds: int,
    log_prefix: str = "native_qt",
) -> dict[str, Any]:
    receipts = run_root / "receipts"
    stdout_path = receipts / f"{log_prefix}_{phase}.stdout.log"
    stderr_path = receipts / f"{log_prefix}_{phase}.stderr.log"
    command = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve()),
        "--child-phase",
        phase,
        "--run-id",
        run_id,
        "--run-root",
        str(run_root.resolve()),
        "--learning-root",
        str(learning_root.resolve()),
    ]
    started = datetime.now(timezone.utc).isoformat()
    timed_out = False
    return_code: int | None = None
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        process = subprocess.Popen(
            command,
            cwd=REPOSITORY_ROOT,
            env=_phase_environment(run_root, learning_root),
            stdout=stdout,
            stderr=stderr,
        )
        try:
            return_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                return_code = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                return_code = process.wait(timeout=30)
    child_receipt_path = receipts / f"native_qt_{phase}.json"
    child_receipt: dict[str, Any] | None = None
    child_receipt_sha: str | None = None
    if child_receipt_path.is_file():
        child_receipt_sha, _ = _hash_file(child_receipt_path, max_bytes=4 * 1024 * 1024)
        child_receipt = json.loads(child_receipt_path.read_text(encoding="utf-8"))
    return {
        "phase": phase,
        "argv": command,
        "started_at_utc": started,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "return_code": return_code,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "stdout_path": str(stdout_path.resolve()),
        "stderr_path": str(stderr_path.resolve()),
        "child_receipt_path": str(child_receipt_path.resolve()),
        "child_receipt_sha256": child_receipt_sha,
        "child_status": None if child_receipt is None else child_receipt.get("status"),
    }


def _read_run_state(run_root: Path) -> dict[str, Any]:
    state_path = run_root / "receipts" / "native_qt_saved_identity.json"
    value = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("native Qt phase state 必須是 JSON object")
    return value


def _orchestrate(run_id: str, *, timeout_seconds: int) -> int:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run-id 僅接受英數、底線與連字號，長度最多 64")
    run_root = RUN_ROOT_BASE / run_id
    learning_output_root = LEARNING_ROOT_BASE / run_id
    preflight, preflight_code = _visible_qt_preflight(run_id)
    if preflight_code != 0:
        print(
            json.dumps(preflight, ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        return preflight_code
    screenshot_evidence = preflight.get("screenshot")
    if (
        not isinstance(screenshot_evidence, dict)
        or screenshot_evidence.get("screen_matches_widget") is not True
        or screenshot_evidence.get("capture_kind")
        != "QScreen.grabWindow_verified_against_QWidget.grab"
    ):
        print(
            json.dumps(
                {
                    "status": "NATIVE_DISPLAY_UNAVAILABLE",
                    "reason": "桌面擷取缺少與指定 Qt widget 的像素核對",
                    "snapshot_copy_started": False,
                    "preflight": preflight,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2
    if run_root.exists() or learning_output_root.exists():
        raise RuntimeError("run／learning root 已存在；請建立新的 run-id，不覆寫既有 QA")
    authority = isolated_launcher._verify_source_snapshot_cli_inputs(
        SNAPSHOT_PATH,
        SNAPSHOT_RECEIPT_PATH,
    )
    learning_output_root.mkdir(parents=True, exist_ok=False)
    (learning_output_root / "recommendation_learning").mkdir(exist_ok=False)
    manifest_path, manifest = isolated_launcher.prepare_isolated_workspace(
        run_root=run_root,
        policy_config_path=run_root / "app_config" / "personal_use_policy.json",
        learning_output_root=learning_output_root,
        authority=authority,
    )
    manifest_sha, _ = _hash_file(manifest_path, max_bytes=4 * 1024 * 1024)
    if manifest_sha != hashlib.sha256(manifest_path.read_bytes()).hexdigest():
        raise RuntimeError("isolated prepare manifest SHA readback mismatch")
    layout = isolated_launcher._runtime_layout(run_root)
    preparation = {
        "schema_version": "native-qt-personal-research-preparation.v1",
        "run_id": run_id,
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_path": str(authority.snapshot_path.resolve()),
        "snapshot_sha256": authority.snapshot_sha256,
        "snapshot_size_bytes": authority.snapshot_size_bytes,
        "snapshot_receipt_path": str(authority.receipt_path.resolve()),
        "snapshot_receipt_sha256": authority.receipt_sha256,
        "isolation_manifest_path": str(manifest_path.resolve()),
        "isolation_manifest_sha256": manifest_sha,
        "run_root": str(run_root.resolve()),
        "data_root_base": str(layout.data_root_base.resolve()),
        "data_root_actual": str(layout.data_root_actual.resolve()),
        "output_root_base": str(layout.output_root_base.resolve()),
        "output_root_actual": str(layout.output_root_actual.resolve()),
        "working_db_path": str(layout.working_db_path.resolve()),
        "working_db_sha256_before_ui": manifest["working_copy"]["working_sha256"],
        "working_db_identity_before_ui": manifest["working_copy"]["working_file_identity"],
        "policy_path": str(layout.policy_config_path.resolve(strict=False)),
        "policy_exists_before_ui": layout.policy_config_path.exists(),
        "personal_capture_root": str(layout.output_root_actual / "personal_prediction"),
        "learning_output_root": str(learning_output_root.resolve()),
        "learning_root": str((learning_output_root / "recommendation_learning").resolve()),
        "learning_tree_sha256_before_ui": manifest["learning_root_read_only_pin"]["tree_pin"]["tree_sha256"],
        "model_enabled_or_tested": False,
        "candidate_root_attached": False,
        "learning_root_empty_before_ui": manifest["learning_root_read_only_pin"]["tree_pin"]["file_count"] == 0,
        "copy_source_kind": "此前建立並固定 SHA 的 repo-ignored QA snapshot；本 runner 不讀 D: source",
        "formal_data_written": False,
        "scheduler_registered": False,
        "http_requested": False,
        "training_or_promotion_started": False,
        "qt_visible_preflight": preflight,
    }
    preparation_path = layout.receipts_dir / "native_qt_preparation.json"
    preparation_sha = _write_json_create_only(preparation_path, preparation)
    phases: list[dict[str, Any]] = []
    for phase in ("first", "restart"):
        outcome = _spawn_phase(
            run_id=run_id,
            phase=phase,
            run_root=run_root,
            learning_root=learning_output_root,
            timeout_seconds=timeout_seconds,
        )
        phases.append(outcome)
        if outcome["return_code"] != 0 or outcome["child_status"] != "PASS":
            break
    state: dict[str, Any] | None = None
    try:
        state = _read_run_state(run_root)
    except Exception:
        pass
    final_status = (
        "PASS_VISIBLE_QT_AUTOMATION"
        if len(phases) == 2
        and all(item["return_code"] == 0 and item["child_status"] == "PASS" for item in phases)
        and state is not None
        else "INCOMPLETE_OR_FAILED"
    )
    db_after: dict[str, Any] | None = None
    try:
        db_after = _stat_identity(layout.working_db_path)
    except OSError:
        pass
    learning_pin_after: dict[str, Any] | None = None
    try:
        learning_pin_after = isolated_launcher._directory_tree_pin(
            learning_output_root / "recommendation_learning"
        )
    except OSError:
        pass
    policy_exists_after = layout.policy_config_path.exists()
    personal_capture_root = layout.output_root_actual / "personal_prediction"
    personal_capture_pin_after: dict[str, Any] | None = None
    if personal_capture_root.exists():
        personal_capture_pin_after = isolated_launcher._directory_tree_pin(personal_capture_root)
    receipt = {
        "schema_version": "native-qt-personal-research-acceptance.v1",
        "run_id": run_id,
        "status": final_status,
        "interaction_classification": "可見 Qt 自動化；由 Qt widget 控件／signals 驅動，不是 Sky 真人點按",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "preflight_receipt_path": str((PRECHECK_ROOT / run_id / "preflight_receipt.json").resolve()),
        "preflight_status": preflight.get("status"),
        "preparation_receipt_path": str(preparation_path.resolve()),
        "preparation_receipt_sha256": preparation_sha,
        "snapshot_source_path": str(authority.snapshot_path.resolve()),
        "snapshot_source_sha256": authority.snapshot_sha256,
        "run_root": str(run_root.resolve()),
        "working_db_path": str(layout.working_db_path.resolve()),
        "working_db_before_ui": preparation["working_db_identity_before_ui"],
        "working_db_after_ui": db_after,
        "policy_path": str(layout.policy_config_path.resolve(strict=False)),
        "policy_exists_before_ui": preparation["policy_exists_before_ui"],
        "policy_exists_after_ui": policy_exists_after,
        "personal_capture_root": preparation["personal_capture_root"],
        "personal_capture_tree_after_ui": personal_capture_pin_after,
        "learning_root": preparation["learning_root"],
        "learning_tree_sha256_before_ui": preparation["learning_tree_sha256_before_ui"],
        "learning_tree_after_ui": learning_pin_after,
        "learning_root_unchanged": (
            learning_pin_after is not None
            and learning_pin_after == manifest["learning_root_read_only_pin"]["tree_pin"]
        ),
        "model_enabled_or_tested": False,
        "phase_receipts": phases,
        "saved_identity": state,
        "limitations": [
            "本輪不附加或啟用校準模型；只驗證 default rule_only 推薦與保存旅程。",
            "QScreen 擷取證明 Qt 視窗可見/有畫面；不等同真人 Sky 操作。",
            "自然成熟績效資料仍依個股研究頁實際 Journey 輸出；unknown/deferred 不算績效 PASS。",
            "不讀正式 D: 資料庫；唯一複製來源是固定 SHA 的 repo-ignored QA snapshot。",
        ],
    }
    if policy_exists_after:
        receipt["status"] = "FAILED_UNEXPECTED_POLICY_WRITE"
    if personal_capture_pin_after and personal_capture_pin_after.get("file_count", 0) != 0:
        receipt["status"] = "FAILED_UNEXPECTED_PERSONAL_CAPTURE"
    if not receipt["learning_root_unchanged"]:
        receipt["status"] = "FAILED_LEARNING_ROOT_CHANGED"
    final_path = layout.receipts_dir / "native_qt_acceptance_receipt.json"
    final_sha = _write_json_create_only(final_path, receipt)
    print(json.dumps({"status": receipt["status"], "receipt_path": str(final_path.resolve()), "receipt_sha256": final_sha, "saved_identity": state}, ensure_ascii=False, indent=2))
    return 0 if receipt["status"] == "PASS_VISIBLE_QT_AUTOMATION" else 3


class _VisibleJourneyDriver:
    """以真實 Qt 控件操作單一 rule-only UI 旅程。"""

    def __init__(self, *, app: Any, window: Any, phase: str, run_id: str, run_root: Path):
        from PySide6.QtCore import QTimer

        self.app = app
        self.window = window
        self.phase = phase
        self.run_id = run_id
        self.run_root = run_root
        self.layout = isolated_launcher._runtime_layout(run_root)
        self.timer = QTimer(window)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.tick)
        self.stage = "exposure"
        self.started = time.monotonic()
        self.step_started = self.started
        self.timeout_seconds = 60 * 35
        self.started_at_utc = datetime.now(timezone.utc).isoformat()
        self.screenshots: list[dict[str, Any]] = []
        self.capture_failures: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.profile: dict[str, str] | None = None
        self.execution_attempts: list[dict[str, Any]] = []
        self.execution_count = 0
        self.expected_result_id = ""
        self.stock_code = ""
        self.result_artifact_hash = ""
        self.rule_event: dict[str, Any] | None = None
        self.error = ""
        self.exit_code = 1
        self.closed_at: float | None = None
        self.screenshot_dir = self.layout.receipts_dir / "screenshots" / phase
        self.screenshot_dir.mkdir(parents=True, exist_ok=False)
        self.state_path = self.layout.receipts_dir / "native_qt_saved_identity.json"
        self.receipt_path = self.layout.receipts_dir / f"native_qt_{phase}.json"
        self._unexpected_modal = False
        self.journey_navigation_done = False

    def _screenshot(self, label: str) -> dict[str, Any]:
        name = f"{self.phase}_{len(self.screenshots) + 1:02d}_{label}.png"
        try:
            capture = _capture_window(self.window, label, self.screenshot_dir / name)
        except ScreenCaptureMismatch as exc:
            self.capture_failures.append(exc.details)
            raise
        self.screenshots.append(capture)
        return capture

    def _action(self, name: str, *, detail: dict[str, Any] | None = None) -> None:
        self.actions.append(
            {
                "sequence": len(self.actions) + 1,
                "action": name,
                "at_utc": datetime.now(timezone.utc).isoformat(),
                "detail": detail or {},
            }
        )

    def _finish(self, status: str, error: str = "") -> None:
        if self.stage == "closing":
            return
        self.error = error
        self.exit_code = 0 if status == "PASS" else 2
        self.final_status = status
        self.stage = "closing"
        self.closed_at = time.monotonic()
        if self.capture_failures:
            self.final_status = "FAILED_SCREENSHOT_IDENTITY"
            self.exit_code = 2
        else:
            try:
                self._screenshot(f"{self.phase}_{status.lower()}")
            except Exception as exc:
                self.final_status = "FAILED_SCREENSHOT"
                self.exit_code = 2
                self.error = f"{error}; 最後截圖失敗：{exc}".strip("; ")
        self.window.close()
        self.step_started = time.monotonic()

    def _profile_choice(self, view: Any) -> dict[str, str]:
        combo = view.profile_combo
        options: list[tuple[int, str, str]] = []
        for index in range(combo.count()):
            profile_id = combo.itemData(index)
            if profile_id is not None:
                options.append((index, str(profile_id), combo.itemText(index)))
        if not options:
            raise RuntimeError("RecommendationView 沒有可用的真實內建 Profile")
        selected = next(
            (item for item in options if "穩健" in item[2] or "保守" in item[2]),
            options[0],
        )
        combo.setCurrentIndex(selected[0])
        self.app.processEvents()
        if combo.currentData() != selected[1]:
            raise RuntimeError("Profile 組合框沒有套用選取的內建 Profile")
        return {"profile_id": selected[1], "display_label": selected[2]}

    def _dismiss_expected_modal(self) -> bool:
        from PySide6.QtWidgets import QDialogButtonBox, QInputDialog, QMessageBox

        modal = self.app.activeModalWidget()
        if modal is None:
            return False
        if self.phase == "first" and isinstance(modal, QInputDialog) and self.stage == "waiting_save":
            modal.setTextValue(f"可見 Qt 個人研究 {self.run_id}")
            buttons = modal.findChild(QDialogButtonBox)
            button = buttons.button(QDialogButtonBox.StandardButton.Ok) if buttons else None
            if button is None:
                self._finish("FAILED", "保存名稱對話框沒有可按的確認按鈕")
                return True
            self._action("確認推薦保存名稱", detail={"dialog_title": modal.windowTitle()})
            button.click()
            return True
        if isinstance(modal, QMessageBox):
            title = modal.windowTitle()
            text = modal.text()
            expected_empty = "目前沒有符合條件的股票" in text
            expected_saved = "推薦結果已保存並完成 canonical readback 驗證" in text
            if expected_empty:
                button = modal.button(QMessageBox.StandardButton.Ok)
                if button is not None:
                    button.click()
                    self._action("確認空結果提示", detail={"dialog_title": title})
                    return True
            if expected_saved:
                button = modal.button(QMessageBox.StandardButton.Ok)
                if button is not None:
                    button.click()
                    self._action("確認保存成功訊息", detail={"dialog_title": title})
                    return True
            if self.stage == "waiting_execution" and "completed" not in text.lower():
                self._finish("FAILED", f"推薦流程出現未預期對話框：{title}／{text[:240]}")
            elif self.stage == "waiting_save":
                self._finish("FAILED", f"保存流程出現未預期對話框：{title}／{text[:240]}")
            return True
        if not self._unexpected_modal:
            self._unexpected_modal = True
            self._finish(
                "FAILED",
                f"出現未預期 modal widget：{type(modal).__name__}／{modal.windowTitle()}",
            )
        return True

    def _apply_advanced_broadening(self, view: Any) -> dict[str, Any]:
        """第二次嘗試只透過 UI 技術指標勾選，不改服務或資料。"""

        changed: list[str] = []
        if view.is_beginner_mode:
            view.mode_btn.click()
            self.app.processEvents()
        for name in (
            "ma_check",
            "adx_check",
            "macd_check",
            "rsi_check",
            "kd_check",
            "bollinger_check",
            "atr_check",
        ):
            widget = getattr(view, name, None)
            if widget is not None and not widget.isChecked():
                widget.click()
                changed.append(name)
        return {"mode": "advanced", "newly_enabled_factors": changed}

    def _start_execution(self, view: Any, *, fallback: bool = False) -> None:
        if self.execution_count >= 2:
            self._finish("FAILED", "兩次真 UI 推薦執行後仍沒有可保存結果")
            return
        self.execution_count += 1
        self.step_started = time.monotonic()
        self.stage = "waiting_execution"
        self._action(
            "點擊執行推薦分析",
            detail={
                "attempt": self.execution_count,
                "fallback": fallback,
                "profile": self.profile,
                "advanced_factors": [
                    name
                    for name in (
                        "ma_check", "adx_check", "macd_check", "rsi_check",
                        "kd_check", "bollinger_check", "atr_check",
                    )
                    if getattr(view, name, None) is not None
                    and getattr(view, name).isChecked()
                ] if not view.is_beginner_mode else [],
            },
        )
        view.execute_btn.click()

    def _record_rule_only_event(self, view: Any) -> None:
        from app_module.personalization_contract import read_personal_use_policy_snapshot_event

        read_model = view.current_read_model
        if read_model is None or read_model.execution is None:
            raise RuntimeError("保存後缺 canonical read model")
        event = read_personal_use_policy_snapshot_event(
            read_model.execution,
            expected_result_id=read_model.result_id,
        )
        if event.get("effective_mode") != "rule_only":
            raise RuntimeError("本次可見 run 不是 rule_only；本輪不驗證模型模式")
        policy_snapshot = event.get("policy_snapshot")
        if not isinstance(policy_snapshot, dict) or policy_snapshot.get("mode") != "rule_only":
            raise RuntimeError("封存政策事件不是 rule_only")
        self.rule_event = {
            "schema_version": event.get("schema_version"),
            "effective_mode": event.get("effective_mode"),
            "requested_mode": event.get("requested_mode"),
            "policy_revision": policy_snapshot.get("revision"),
            "policy_sha256": policy_snapshot.get("policy_sha256"),
            "source_time_basis": event.get("source_time_basis"),
            "official_historical_pit_verified": event.get("official_historical_pit_verified"),
        }

    def _go_to_journey(self) -> None:
        from PySide6.QtWidgets import QTabWidget

        if self.journey_navigation_done:
            return
        workspace = getattr(self.window, "stock_research_workspace", None)
        if workspace is None or workspace.journey_view is None:
            raise RuntimeError("MainWindow 沒有 Decision → Result Journey 視圖")
        tabs = workspace.report_tabs
        journey_index = next(
            (i for i in range(tabs.count()) if "決策" in tabs.tabText(i) and "結果" in tabs.tabText(i)),
            None,
        )
        if not isinstance(tabs, QTabWidget) or journey_index is None:
            raise RuntimeError("找不到真實『決策 → 結果』分頁")
        tabs.setCurrentIndex(journey_index)
        self.journey_navigation_done = True
        self._action("切換個股研究的決策結果分頁", detail={"tab_text": tabs.tabText(journey_index)})

    def _journey_ready(self) -> bool:
        workspace = getattr(self.window, "stock_research_workspace", None)
        journey_view = getattr(workspace, "journey_view", None)
        journey = getattr(journey_view, "journey", None)
        return bool(
            journey is not None
            and journey.recommendation_result_id == self.expected_result_id
            and journey.recommendation_result.result_id == self.expected_result_id
        )

    def _complete_first(self, view: Any) -> None:
        result_id = view._verified_saved_result_id()
        read_model = view.current_read_model
        receipt = view.current_save_receipt
        if not result_id or result_id != view.current_execution.result_id:
            raise RuntimeError("真 UI save/readback 沒有提供一致的 verified result_id")
        if read_model is None or receipt is None:
            raise RuntimeError("真 UI save/readback 缺少 saved read model／write receipt")
        if read_model.integrity_basis != "canonical_payload_and_index_verified":
            raise RuntimeError("保存結果未經 canonical payload/index 驗證")
        self._record_rule_only_event(view)
        self.expected_result_id = result_id
        self.stock_code = view._selected_stock_code()
        if not self.stock_code:
            raise RuntimeError("保存後沒有 selected stock identity")
        self.result_artifact_hash = str(read_model.raw_artifact_sha256)
        self._screenshot("first_saved_canonical_result")
        if not view.personal_choice_controls.adopt_button.isEnabled():
            raise RuntimeError("已驗證保存後個人採用控件仍停用")
        view.personal_choice_controls.adopt_button.click()
        self._action(
            "點擊個人採用",
            detail={"result_id": result_id, "stock_code": self.stock_code},
        )
        self.stage = "waiting_choice"
        self.step_started = time.monotonic()

    def _save_identity_state(self, view: Any) -> None:
        workspace = getattr(self.window, "stock_research_workspace", None)
        journey_view = getattr(workspace, "journey_view", None)
        journey = getattr(journey_view, "journey", None)
        maturity = []
        if journey is not None:
            maturity = [item.to_dict() for item in journey.outcome_maturity]
        payload = {
            "schema_version": "native-qt-saved-identity.v1",
            "run_id": self.run_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "result_id": self.expected_result_id,
            "stock_code": self.stock_code,
            "canonical_payload_hash": str(view.current_read_model.payload_hash),
            "raw_artifact_sha256": self.result_artifact_hash,
            "artifact_location": str(view.current_read_model.artifact_location),
            "persisted_at": view.current_read_model.persisted_at.isoformat(),
            "profile": self.profile,
            "policy_event": self.rule_event,
            "personal_choice_ui_status": view.personal_choice_controls.status_label.text(),
            "journey_result_id": None if journey is None else journey.recommendation_result_id,
            "journey_status": None if journey is None else journey.status.value,
            "journey_market_data_as_of_date": (
                None if journey is None else journey.recommendation_result.market_data_as_of_date
            ),
            "outcome_maturity": maturity,
            "all_operations_via_qt_widgets": True,
            "model_enabled_or_tested": False,
            "formal_data_written": False,
            "training_or_promotion_started": False,
            "scheduler_registered": False,
        }
        _write_json_create_only(self.state_path, payload)

    def tick(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        if time.monotonic() - self.started > self.timeout_seconds:
            self._finish("TIMEOUT", f"旅程超過 {self.timeout_seconds} 秒")
            return
        if self.stage == "closing":
            if not self.window.isVisible():
                self.timer.stop()
                self.app.exit(self.exit_code)
                return
            if self.closed_at is not None and time.monotonic() - self.closed_at > 90:
                self.timer.stop()
                self.app.exit(2)
                return
            return
        if self._dismiss_expected_modal():
            return
        try:
            if self.stage == "exposure":
                handle = self.window.windowHandle()
                if not self.window.isVisible() or handle is None or not handle.isExposed():
                    if time.monotonic() - self.step_started > 10:
                        raise RuntimeError("MainWindow 未在 10 秒內顯示於桌面")
                    return
                capture = self._screenshot("mainwindow_initial")
                if capture["width"] < 640 or capture["height"] < 480:
                    raise RuntimeError("MainWindow 擷取影像尺寸不足，疑似最小化／遮蔽")
                if self.phase == "first":
                    navigation = getattr(self.window, "left_navigation", None)
                    button = navigation.button_for_key("recommendation") if navigation else None
                    if button is None:
                        raise RuntimeError("MainWindow 缺推薦分析導覽按鈕")
                    button.click()
                    self._action("點擊推薦分析導覽", detail={"workspace": "recommendation"})
                    self.stage = "recommendation_ready"
                else:
                    navigation = getattr(self.window, "left_navigation", None)
                    button = navigation.button_for_key("recommendation") if navigation else None
                    if button is None:
                        raise RuntimeError("MainWindow 缺推薦分析導覽按鈕")
                    button.click()
                    self._action("點擊推薦分析導覽", detail={"workspace": "recommendation"})
                    self.stage = "reload_ready"
                return

            view = getattr(self.window, "recommendation_view", None)
            if view is None:
                raise RuntimeError("MainWindow 沒有 RecommendationView")

            if self.stage == "recommendation_ready":
                if self.window.left_navigation.current_key() != "recommendation":
                    return
                mode_combo = getattr(view, "personal_policy_mode_combo", None)
                rule_only_index = mode_combo.findData("rule_only") if mode_combo else -1
                if rule_only_index < 0:
                    raise RuntimeError("個人政策組合框沒有可選 rule_only 模式")
                mode_combo.setCurrentIndex(rule_only_index)
                self.app.processEvents()
                if mode_combo.currentData() != "rule_only":
                    raise RuntimeError("推薦執行前無法固定為 rule_only")
                self._screenshot("recommendation_workspace")
                self.profile = self._profile_choice(view)
                self._screenshot("rule_only_profile_selected")
                self._start_execution(view)
                return

            if self.stage == "waiting_execution":
                execution = getattr(view, "current_execution", None)
                worker = getattr(view, "worker", None)
                running = False
                if worker is not None:
                    try:
                        running = worker.isRunning()
                    except RuntimeError:
                        running = False
                if execution is None or running or not view.execute_btn.isEnabled():
                    return
                rows = tuple(getattr(execution, "items", ()) or ())
                self.execution_attempts.append(
                    {
                        "attempt": self.execution_count,
                        "result_id": str(getattr(execution, "result_id", "")),
                        "status": str(getattr(getattr(execution, "status", None), "value", "")),
                        "recommendation_count": len(rows),
                    }
                )
                if not rows:
                    if self.execution_count == 1:
                        self._screenshot("first_attempt_no_recommendations")
                        changed = self._apply_advanced_broadening(view)
                        self._action("透過進階 UI 擴展技術訊號", detail=changed)
                        self._start_execution(view, fallback=True)
                        return
                    raise RuntimeError("兩次真 UI 推薦執行後仍無可保存推薦列")
                self._screenshot("recommendation_results")
                view.results_table.selectRow(0)
                self.app.processEvents()
                self.stock_code = view._selected_stock_code()
                if not self.stock_code:
                    raise RuntimeError("QTableView 選列後沒有 selected stock code")
                if not view.save_result_btn.isVisible() or not view.save_result_btn.isEnabled():
                    raise RuntimeError("推薦結果出現但保存控件不可操作")
                self._screenshot("selected_recommendation_stock")
                self.stage = "waiting_save"
                self.step_started = time.monotonic()
                view.save_result_btn.click()
                self._action("點擊保存結果", detail={"stock_code": self.stock_code})
                return

            if self.stage == "waiting_save":
                result_id = view._verified_saved_result_id()
                if not result_id:
                    if time.monotonic() - self.step_started > 45:
                        raise RuntimeError("保存完成後未讀回 verified canonical result")
                    return
                self._complete_first(view)
                return

            if self.stage == "waiting_choice":
                status = view.personal_choice_controls.status_label.text()
                if "最近一次個人決定：個人採用" not in status:
                    if time.monotonic() - self.step_started > 45:
                        raise RuntimeError("UI 未 fresh-readback 本次個人採用選擇")
                    return
                self._screenshot("personal_choice_saved")
                if not view.stock_research_btn.isEnabled():
                    raise RuntimeError("個股研究下鑽按鈕不可操作")
                view.stock_research_btn.click()
                self._action(
                    "點擊查看個股研究",
                    detail={"result_id": self.expected_result_id, "stock_code": self.stock_code},
                )
                self.stage = "waiting_first_journey"
                self.step_started = time.monotonic()
                return

            if self.stage == "waiting_first_journey":
                if self.window.left_navigation.current_key() != "stock_research":
                    return
                self._go_to_journey()
                if not self._journey_ready():
                    if time.monotonic() - self.step_started > 90:
                        raise RuntimeError("個股研究的 Decision → Result 沒有 exact result readback")
                    return
                self._screenshot("first_exact_journey_readback")
                self._save_identity_state(view)
                for key in ("watchlist", "portfolio"):
                    navigation = self.window.left_navigation
                    button = navigation.button_for_key(key)
                    if button is not None and button.isEnabled():
                        button.click()
                        self.app.processEvents()
                        self._action("點擊工作區導覽", detail={"workspace": key})
                        self._screenshot(f"workspace_{key}")
                self._finish("PASS")
                return

            if self.stage == "reload_ready":
                if self.window.left_navigation.current_key() != "recommendation":
                    return
                self._screenshot("restart_recommendation_workspace")
                view.saved_result_id_input.setText(self.expected_result_id)
                self._action("輸入精確已保存 result_id", detail={"result_id": self.expected_result_id})
                self.stage = "waiting_reload"
                self.step_started = time.monotonic()
                view.load_saved_result_button.click()
                self._action("點擊讀取單筆已保存結果")
                return

            if self.stage == "waiting_reload":
                actual_id = view._verified_saved_result_id()
                if actual_id != self.expected_result_id:
                    if time.monotonic() - self.step_started > 90:
                        raise RuntimeError(
                            f"fresh MainWindow exact saved readback 不一致：{actual_id!r}"
                        )
                    return
                read_model = view.current_read_model
                if read_model is None or read_model.execution is None:
                    raise RuntimeError("fresh MainWindow 沒有 canonical loaded read model")
                if str(read_model.raw_artifact_sha256) != self.result_artifact_hash:
                    raise RuntimeError("fresh MainWindow readback 的 canonical artifact SHA 改變")
                frame = view.recommendations_model.getDataFrame()
                row_index = next(
                    (
                        index
                        for index, value in enumerate(frame.get("證券代號", ()))
                        if str(value).strip() == self.stock_code
                    ),
                    None,
                )
                if row_index is None:
                    raise RuntimeError("fresh saved result 缺原 selected stock row")
                view.results_table.selectRow(row_index)
                self.app.processEvents()
                self._screenshot("restart_exact_result_loaded")
                status = view.personal_choice_controls.status_label.text()
                if "最近一次個人決定：個人採用" not in status:
                    raise RuntimeError("fresh MainWindow 沒有讀回 exact 個人採用 Journal 選擇")
                self._screenshot("restart_choice_readback")
                if not view.stock_research_btn.isEnabled():
                    raise RuntimeError("fresh loaded result 的個股研究下鑽不可操作")
                view.stock_research_btn.click()
                self._action("重啟後點擊查看個股研究", detail={"result_id": actual_id})
                self.stage = "waiting_restart_journey"
                self.step_started = time.monotonic()
                return

            if self.stage == "waiting_restart_journey":
                if self.window.left_navigation.current_key() != "stock_research":
                    return
                self._go_to_journey()
                if not self._journey_ready():
                    if time.monotonic() - self.step_started > 90:
                        raise RuntimeError("重啟後 Journey 未讀回同一 result_id")
                    return
                self._screenshot("restart_exact_journey_readback")
                journey = self.window.stock_research_workspace.journey_view.journey
                if journey.recommendation_result.market_data_as_of_date is None:
                    self._action(
                        "重啟後 Journey 顯示行情日期未知",
                        detail={"result_id": self.expected_result_id},
                    )
                self._finish("PASS")
                return
        except Exception as exc:
            self._finish("FAILED", f"{type(exc).__name__}: {exc}")

    def run(self) -> int:
        self.timer.start()
        return int(self.app.exec())

    def receipt(self) -> dict[str, Any]:
        layout = self.layout
        result: dict[str, Any] = {
            "schema_version": "native-qt-visible-phase-receipt.v1",
            "phase": self.phase,
            "run_id": self.run_id,
            "status": getattr(self, "final_status", "FAILED"),
            "error": self.error,
            "started_at_utc": self.started_at_utc,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "process_id": os.getpid(),
            "qt_platform_requested": os.environ.get("QT_QPA_PLATFORM"),
            "data_root": os.environ.get("DATA_ROOT"),
            "output_root": os.environ.get("OUTPUT_ROOT"),
            "profile": os.environ.get("PROFILE"),
            "learning_output_root": os.environ.get("RECOMMENDATION_LEARNING_OUTPUT_ROOT"),
            "run_root": str(self.run_root.resolve()),
            "working_db_path": str(layout.working_db_path.resolve()),
            "policy_path": str(layout.policy_config_path.resolve(strict=False)),
            "window_title": self.window.windowTitle(),
            "window_id": int(self.window.winId()),
            "window_exposed": bool(
                self.window.isVisible()
                and self.window.windowHandle() is not None
                and self.window.windowHandle().isExposed()
            ),
            "screenshots": self.screenshots,
            "screen_capture_failures": self.capture_failures,
            "actions": self.actions,
            "selected_profile": self.profile,
            "execution_attempts": self.execution_attempts,
            "result_id": self.expected_result_id or None,
            "stock_code": self.stock_code or None,
            "raw_artifact_sha256": self.result_artifact_hash or None,
            "policy_event": self.rule_event,
            "model_enabled_or_tested": False,
            "all_business_actions_via_qt_widgets": True,
            "canonical_query_used_only_as_ui_readback": True,
            "formal_data_written": False,
            "scheduler_registered": False,
            "http_requested": False,
            "training_or_promotion_started": False,
        }
        return result


def _child_phase(args: argparse.Namespace) -> int:
    from PySide6.QtWidgets import QApplication
    from data_module.config import TWStockConfig

    run_root = args.run_root.resolve(strict=True)
    learning_root = args.learning_root.resolve(strict=True)
    layout = isolated_launcher._runtime_layout(run_root)
    manifest = isolated_launcher._read_manifest(layout.receipts_dir / "isolation_manifest.json")
    if manifest.get("profile") != "test" or manifest.get("run_root") != str(run_root):
        raise RuntimeError("phase 子程序的隔離 manifest 身分不符")
    config = TWStockConfig()
    isolated_launcher._verify_test_profile_config(config, layout)
    config_env = _phase_environment(run_root, learning_root)
    for key, value in config_env.items():
        if key in {"DATA_ROOT", "OUTPUT_ROOT", "PROFILE", "RECOMMENDATION_LEARNING_OUTPUT_ROOT", "QT_QPA_PLATFORM"}:
            os.environ[key] = value

    from ui_qt.main import MainWindow, apply_app_theme

    phase = args.child_phase
    if phase not in {"first", "restart"}:
        raise RuntimeError("child phase 缺少有效的 phase")
    app = QApplication([str(Path(__file__).resolve()), "--child-phase", phase])
    app.setOrganizationName("TechnicalAnalysis")
    app.setApplicationName("TechnicalAnalysis")
    apply_app_theme(app)
    window = MainWindow(policy_config_path=layout.policy_config_path)
    view = getattr(window, "recommendation_view", None)
    policy = getattr(view, "_personal_use_policy", None)
    if policy is None or getattr(policy, "mode", None) != "rule_only":
        raise RuntimeError("fresh QA MainWindow 沒有載入明示的 rule_only 個人政策")
    if layout.policy_config_path.exists():
        raise RuntimeError("rule_only 冷啟動意外寫入政策檔")
    window.setWindowTitle(f"{WINDOW_TITLE_PREFIX}｜{phase}｜{args.run_id}")
    window.resize(1440, 900)
    driver = _VisibleJourneyDriver(
        app=app,
        window=window,
        phase=phase,
        run_id=args.run_id,
        run_root=run_root,
    )
    window.show()
    window.raise_()
    window.activateWindow()
    result_id = ""
    stock_code = ""
    artifact_hash = ""
    if phase == "restart":
        saved_state = _read_run_state(run_root)
        result_id = str(saved_state["result_id"])
        stock_code = str(saved_state["stock_code"])
        artifact_hash = str(saved_state["raw_artifact_sha256"])
        driver.expected_result_id = result_id
        driver.stock_code = stock_code
        driver.result_artifact_hash = artifact_hash
    code = driver.run()
    receipt = driver.receipt()
    receipt_path = layout.receipts_dir / f"native_qt_{phase}.json"
    _write_json_create_only(receipt_path, receipt)
    print(json.dumps({"phase": phase, "status": receipt["status"], "receipt": str(receipt_path)}, ensure_ascii=False))
    return code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="以固定 QA snapshot 複本操作真 MainWindow 的可見 Qt 規則模式驗收。"
    )
    parser.add_argument("--run-id", default="native_qt_wp3_20260928_01")
    parser.add_argument("--timeout-seconds", type=int, default=60 * 35)
    parser.add_argument(
        "--child-phase",
        choices=("first", "restart"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--run-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--learning-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument(
        "--mainwindow-capture-probe",
        action="store_true",
        help="僅顯示 --run-id 指定且已準備好的新 MainWindow 並核對擷取來源；不執行業務操作",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.child_phase:
        if args.run_root is None or args.learning_root is None:
            parser.error("child phase requires internal run/learning roots")
        return _child_phase(args)
    try:
        if args.mainwindow_capture_probe:
            if args.preflight_only:
                parser.error("--mainwindow-capture-probe 與 --preflight-only 不可併用")
            try:
                _capture_probe_workspace_paths(args.run_id)
            except ValueError as exc:
                parser.error(str(exc))
            return _mainwindow_capture_probe(args.run_id)
        if args.preflight_only:
            receipt, code = _visible_qt_preflight(args.run_id)
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
            return code
        return _orchestrate(args.run_id, timeout_seconds=args.timeout_seconds)
    except Exception as exc:
        print(f"可見 Qt 個人研究驗收停止：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
