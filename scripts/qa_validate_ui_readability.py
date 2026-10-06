"""隔離驗證主視窗各工作區的首屏、進階展開與窄桌面可讀性。

這個 runner 只建立使用隔離 ``DATA_ROOT``／``OUTPUT_ROOT`` 的實際
``MainWindow``，不啟動排程、collector 或正式資料更新。證據同時記錄
requested／actual window、shell 內容尺寸、可見 CTA、水平捲軸與進階控制項，
避免把獨立 view 的固定尺寸誤當成主視窗可讀性。
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


DEFAULT_SCALES = ("1.25", "1.5")
VIEWPORTS = ((1280, 800), (1024, 768))
WORKSPACE_KEYS = (
    "workbench",
    "market_explore",
    "recommendation",
    "backtest",
    "watchlist",
    "portfolio",
    "update",
    "runtime",
)
ADVANCED_TOKENS = ("進階", "詳細", "診斷", "來源與", "逐項")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="隔離 MainWindow UI 可讀性證據 runner")
    parser.add_argument(
        "--scale",
        action="append",
        dest="scales",
        help="Qt scale factor；可重複指定，預設為 1.25 與 1.5",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path("output") / "qa" / "incident_20260921" / "ui_readability"),
        help="隔離 evidence 輸出目錄",
    )
    parser.add_argument("--_child", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args._child:
        scale = os.environ.get("QT_SCALE_FACTOR", "")
        evidence_path = output_dir / "evidence.json"
        try:
            evidence = _run_child(scale=scale, output_dir=output_dir)
            evidence_path.write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"UI readability evidence written: {evidence_path}")
            return 0
        except BaseException as exc:  # noqa: BLE001 - evidence must explain failure
            evidence_path.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "evidence_kind": "offscreen_mainwindow_readability",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"UI readability runner failed: {exc}", file=sys.stderr)
            return 1

    scales = tuple(args.scales or DEFAULT_SCALES)
    if not scales:
        raise ValueError("至少需要一個 --scale")
    results: list[dict[str, Any]] = []
    script_path = Path(__file__).resolve()
    for scale in scales:
        _validate_scale(scale)
        scale_dir = output_dir / f"scale_{scale.replace('.', '_')}"
        scale_dir.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["QT_SCALE_FACTOR"] = scale
        environment["PYTHONIOENCODING"] = "utf-8"
        completed = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--_child",
                "--output-dir",
                str(scale_dir),
            ],
            cwd=str(script_path.parents[1]),
            env=environment,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="backslashreplace",
            timeout=300,
            check=False,
        )
        evidence_path = scale_dir / "evidence.json"
        if completed.returncode != 0 or not evidence_path.exists():
            raise RuntimeError(
                "offscreen MainWindow readability child failed "
                f"scale={scale!r}, returncode={completed.returncode}, "
                f"stdout_tail={completed.stdout[-1600:]!r}, "
                f"stderr_tail={completed.stderr[-1600:]!r}"
            )
        result = json.loads(evidence_path.read_text(encoding="utf-8"))
        if result.get("status") != "passed":
            raise RuntimeError(f"offscreen child reported failure: {result}")
        results.append(result)

    summary = {
        "status": "passed",
        "evidence_kind": "offscreen_mainwindow_readability",
        "native_windows_interaction": "unavailable_without_cua_trusted_rpc",
        "screenreader": "not_tested",
        "scales": results,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_matrix_markdown(summary, output_dir / "inventory_matrix.md")
    print(f"UI readability validation passed: {summary_path}")
    return 0


def _validate_scale(value: str) -> None:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"scale 必須是正數：{value!r}") from exc
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"scale 必須是正數：{value!r}")


def _run_child(*, scale: str, output_dir: Path) -> dict[str, Any]:
    _validate_scale(scale)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    project_root = Path(__file__).resolve().parents[1]
    isolated_root = output_dir / "_isolated_app"
    os.environ["DATA_ROOT"] = str(isolated_root / "data")
    os.environ["OUTPUT_ROOT"] = str(isolated_root / "output")
    os.environ["PROFILE"] = "prod"
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import (
        QApplication,
        QAbstractButton,
        QGroupBox,
        QLabel,
        QMainWindow,
        QPushButton,
        QScrollArea,
        QScrollBar,
        QTabWidget,
    )

    from ui_qt.main import MainWindow, apply_app_theme

    existing_app = QApplication.instance()
    app = existing_app if isinstance(existing_app, QApplication) else QApplication(sys.argv)
    apply_app_theme(app)
    window = MainWindow()
    try:
        window.show()
        app.processEvents()
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            raise AssertionError("offscreen Qt 沒有 primary screen")
        observed_scale = float(screen.devicePixelRatio())
        requested_scale = float(scale)
        if not math.isclose(observed_scale, requested_scale, rel_tol=0, abs_tol=0.01):
            raise AssertionError(
                f"Qt scale factor 不符：requested={requested_scale}, observed={observed_scale}"
            )

        viewport_results: list[dict[str, Any]] = []
        for requested_width, requested_height in VIEWPORTS:
            # The prior viewport is pinned below; release that pin before
            # measuring the next natural size and minimum-size constraint.
            window.setMinimumSize(0, 0)
            window.setMaximumSize(16_777_215, 16_777_215)
            window.resize(requested_width, requested_height)
            app.processEvents()
            natural_size = window.size()
            natural_minimum_size = window.minimumSize()
            # Pin after the first pass so a child sizeHint cannot silently grow
            # the requested viewport; actual size is still recorded and checked.
            window.setFixedSize(requested_width, requested_height)
            app.processEvents()
            actual_size = window.size()
            if actual_size.width() != requested_width or actual_size.height() != requested_height:
                raise AssertionError(
                    "MainWindow viewport was constrained by a minimum size: "
                    f"requested={requested_width}x{requested_height}, "
                    f"actual={actual_size.width()}x{actual_size.height()}"
                )
            viewport_results.append(
                _inspect_viewport(
                    window,
                    app,
                    output_dir,
                    requested_width,
                    requested_height,
                    requested_scale,
                    natural_size,
                    natural_minimum_size,
                    QAbstractButton,
                    QGroupBox,
                    QLabel,
                    QMainWindow,
                    QPushButton,
                    QScrollArea,
                    QScrollBar,
                    QTabWidget,
                    Qt,
                )
            )

        return {
            "status": "passed",
            "evidence_kind": "offscreen_mainwindow_readability",
            "native_windows_interaction": "not_observed",
            "screenreader": "not_tested",
            "scale_factor_requested": requested_scale,
            "scale_factor_observed": observed_scale,
            "viewports": viewport_results,
        }
    finally:
        window.close()
        app.processEvents()
        app.quit()


def _inspect_viewport(
    window: Any,
    app: Any,
    output_dir: Path,
    requested_width: int,
    requested_height: int,
    requested_scale: float,
    natural_size: Any,
    natural_minimum_size: Any,
    QAbstractButton: Any,
    QGroupBox: Any,
    QLabel: Any,
    QMainWindow: Any,
    QPushButton: Any,
    QScrollArea: Any,
    QScrollBar: Any,
    QTabWidget: Any,
    Qt: Any,
) -> dict[str, Any]:
    del QMainWindow
    navigation = window.left_navigation
    shell = window.centralWidget()
    stack = window.workspace_stack
    actual_size = window.size()
    screenshot_stem = f"scale_{str(requested_scale).replace('.', '_')}_{requested_width}x{requested_height}"
    window_screenshot = output_dir / f"{screenshot_stem}_mainwindow.png"
    if not window.grab().save(str(window_screenshot)):
        raise AssertionError("MainWindow screenshot 保存失敗")

    pages: list[dict[str, Any]] = []
    for key in WORKSPACE_KEYS:
        window._select_main_workspace(key)
        app.processEvents()
        page = window.workspace_widgets.get(key)
        if page is None:
            raise AssertionError(f"實際工作區不存在：{key}")
        advanced = _expand_readability_controls(page, QAbstractButton, QGroupBox)
        app.processEvents()
        page_snapshot = _page_snapshot(
            page,
            QAbstractButton,
            QLabel,
            QPushButton,
            QScrollArea,
            QScrollBar,
        )
        page_screenshot = output_dir / f"{screenshot_stem}_{key}.png"
        if not page.grab().save(str(page_screenshot)):
            raise AssertionError(f"工作區 screenshot 保存失敗：{key}")
        pages.append(
            {
                "page_key": key,
                "tab_targets": _inspect_tabs(
                    page,
                    key,
                    app,
                    QTabWidget,
                    QAbstractButton,
                    QGroupBox,
                    QLabel,
                    QPushButton,
                    QScrollArea,
                    QScrollBar,
                ),
                "advanced_controls_expanded": advanced,
                "page_snapshot": page_snapshot,
                "screenshot": str(page_screenshot),
            }
        )

    return {
        "requested_viewport": {"width": requested_width, "height": requested_height},
        "actual_viewport": {
            "width": int(actual_size.width()),
            "height": int(actual_size.height()),
        },
        "natural_viewport_before_pin": {
            "width": int(natural_size.width()),
            "height": int(natural_size.height()),
        },
        "minimum_size_before_pin": {
            "width": int(natural_minimum_size.width()),
            "height": int(natural_minimum_size.height()),
        },
        "shell_size": {"width": int(shell.size().width()), "height": int(shell.size().height())},
        "navigation_size": {
            "width": int(navigation.width()),
            "height": int(navigation.height()),
            "collapsed": bool(navigation.is_collapsed()),
        },
        "workspace_stack_size": {
            "width": int(stack.width()),
            "height": int(stack.height()),
        },
        "pages": pages,
        "mainwindow_screenshot": str(window_screenshot),
    }


def _expand_readability_controls(page: Any, QAbstractButton: Any, QGroupBox: Any) -> list[str]:
    expanded: list[str] = []
    controls = list(page.findChildren(QGroupBox)) + list(page.findChildren(QAbstractButton))
    for control in controls:
        if not control.isVisible() or not control.isCheckable():
            continue
        label = str(control.title() if isinstance(control, QGroupBox) else control.text())
        if not any(token in label for token in ADVANCED_TOKENS):
            continue
        if not control.isChecked():
            control.setChecked(True)
        expanded.append(label or control.objectName())
    return expanded


def _inspect_tabs(
    page: Any,
    key: str,
    app: Any,
    QTabWidget: Any,
    QAbstractButton: Any,
    QGroupBox: Any,
    QLabel: Any,
    QPushButton: Any,
    QScrollArea: Any,
    QScrollBar: Any,
) -> list[dict[str, Any]]:
    tab_widgets: list[Any] = []
    if isinstance(page, QTabWidget):
        tab_widgets.append(page)
    tab_widgets.extend(page.findChildren(QTabWidget))
    snapshots: list[dict[str, Any]] = []
    for tabs in tab_widgets:
        for index in range(tabs.count()):
            tabs.setCurrentIndex(index)
            app.processEvents()
            tab_page = tabs.currentWidget()
            if tab_page is None:
                continue
            advanced = _expand_readability_controls(tab_page, QAbstractButton, QGroupBox)
            app.processEvents()
            snapshots.append(
                {
                    "target": f"{key}:{tabs.tabText(index)}",
                    "advanced_controls_expanded": advanced,
                    "page_snapshot": _page_snapshot(
                        tab_page,
                        QAbstractButton,
                        QLabel,
                        QPushButton,
                        QScrollArea,
                        QScrollBar,
                    ),
                }
            )
    return snapshots


def _page_snapshot(
    page: Any,
    QAbstractButton: Any,
    QLabel: Any,
    QPushButton: Any,
    QScrollArea: Any,
    QScrollBar: Any,
) -> dict[str, Any]:
    visible_buttons = [
        button
        for button in page.findChildren(QAbstractButton)
        if button.isVisible() and str(button.text()).strip()
    ]
    cta_candidates = [
        str(button.text()).strip()
        for button in visible_buttons
        if isinstance(button, QPushButton) and button.isEnabled()
    ]
    unclipped_labels = []
    for label in page.findChildren(QLabel):
        if not label.isVisible() or label.wordWrap() or label.width() <= 0:
            continue
        if label.sizeHint().width() > label.width() + 8:
            unclipped_labels.append(label.objectName() or label.text()[:40])
    horizontal_scrollbars = [
        scroll
        for scroll in page.findChildren(QScrollBar)
        if scroll.isVisible() and scroll.orientation().name == "Horizontal"
    ]
    return {
        "visible": bool(page.isVisible()),
        "size": {"width": int(page.width()), "height": int(page.height())},
        "minimum_size_hint": {
            "width": int(page.minimumSizeHint().width()),
            "height": int(page.minimumSizeHint().height()),
        },
        "enabled_cta_count": len(cta_candidates),
        "enabled_cta_labels": cta_candidates[:12],
        "unclipped_single_line_labels": unclipped_labels[:12],
        "horizontal_scrollbar_count": len(horizontal_scrollbars),
        "nested_scroll_area_count": len(page.findChildren(QScrollArea)),
    }


def _write_matrix_markdown(summary: dict[str, Any], path: Path) -> None:
    rows = [
        "# UI 可讀性實證矩陣（隔離 MainWindow）",
        "",
        "| Scale | Requested | Actual | Page | Advanced expanded | H-scroll | Nested scroll | Enabled CTA |",
        "|---|---:|---:|---|---:|---:|---:|---:|",
    ]
    for scale_result in summary.get("scales", []):
        scale = scale_result.get("scale_factor_requested", "?")
        for viewport in scale_result.get("viewports", []):
            requested = viewport["requested_viewport"]
            actual = viewport["actual_viewport"]
            size_text = f"{requested['width']}×{requested['height']}"
            actual_text = f"{actual['width']}×{actual['height']}"
            for page in viewport.get("pages", []):
                snapshot = page["page_snapshot"]
                rows.append(
                    "| {scale} | {requested} | {actual} | {page} | {advanced} | {hscroll} | {nested} | {cta} |".format(
                        scale=scale,
                        requested=size_text,
                        actual=actual_text,
                        page=page["page_key"],
                        advanced="、".join(page["advanced_controls_expanded"]) or "—",
                        hscroll=snapshot["horizontal_scrollbar_count"],
                        nested=snapshot["nested_scroll_area_count"],
                        cta=snapshot["enabled_cta_count"],
                    )
                )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
