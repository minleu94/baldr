"""以真實 MainWindow production wiring 驗證跨頁研究旅程。

這個 runner 只把本次測試的 ``DATA_ROOT``／``OUTPUT_ROOT`` 指到隔離目錄，
再經由 RecommendationService、sealed execution、RecommendationView 正式保存／
canonical 查回、實際 Qt signal 與 append-only journal 走完：推薦結果 → 個股研究 →
納入／略過／筆記／下次檢視 → 觀察清單 →
同一推薦結果的同一股票 → Workbench → 同程序 MainWindow 關閉後重建與
磁碟讀回。

fixture 使用隔離的 synthetic market frame 與固定 Decimal scorer，並由真實
RecommendationService 產生及保存推薦 execution；不宣稱
正式行情、券商資料、Evidence 或實際交易已驗證。Qt 使用 offscreen，因此
畫面證據是實際 widget 的中文畫面截圖，不等同 Windows 前景焦點或螢幕閱讀器
驗證。
"""

from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal
import faulthandler
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable
from uuid import uuid4


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="隔離 offscreen MainWindow 跨頁研究旅程 QA runner"
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path("output") / "qa" / "research_journey_qt"),
        help="evidence 輸出根目錄；每次執行會建立新的 run 子目錄",
    )
    parser.add_argument(
        "--mode",
        choices=(
            "journey",
            "task_worker_lifecycle",
            "mainwindow_shutdown",
            "continuity_readback",
        ),
        default="journey",
        help=(
            "QA 模式；task_worker_lifecycle 為最小 worker 驗證，"
            "mainwindow_shutdown 驗證真 MainWindow 關閉，"
            "continuity_readback 從另一個 child 讀回 durable state"
        ),
    )
    parser.add_argument(
        "--shared-root",
        default=None,
        help=(
            "跨獨立 child 共用的隔離 DATA_ROOT／OUTPUT_ROOT；"
            "僅 continuity_readback 或明確要求 journey writer 時使用"
        ),
    )
    return parser.parse_args(argv)


def _configure_console_streams() -> None:
    """讓 child 的 help／錯誤訊息不受 Windows code page 影響。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            continue


def _update_child_process_metadata(path: Path, **updates: Any) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            payload = {}
    except (OSError, json.JSONDecodeError):
        payload = {}
    payload.update(updates)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _evidence_kind_for_mode(mode: str) -> str:
    if mode == "task_worker_lifecycle":
        return "qt_task_worker_lifecycle"
    if mode == "mainwindow_shutdown":
        return "qt_mainwindow_shutdown_lifecycle"
    if mode == "continuity_readback":
        return "qt_continuity_cross_process_readback"
    return "offscreen_qt_production_mainwindow"


def main(argv: list[str] | None = None) -> int:
    _configure_console_streams()
    args = parse_args(argv)
    evidence_kind = _evidence_kind_for_mode(args.mode)
    output_root = Path(args.output_dir).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = output_root / (
        f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    summary_path = output_root / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "status": "running",
                "evidence_kind": evidence_kind,
                "run_dir": str(run_dir),
                "started_at": datetime.now().isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    child_process_metadata_path = run_dir / "child_process.json"
    _update_child_process_metadata(
        child_process_metadata_path,
        status="starting",
        pid=os.getpid(),
        ppid=getattr(os, "getppid", lambda: 0)(),
        started_at=datetime.now().astimezone().isoformat(),
        mode=args.mode,
        executable=sys.executable,
        argv0=sys.argv[0] if sys.argv else "",
        cwd=str(Path.cwd()),
    )

    process_error_mode = _configure_child_process_error_mode()
    _update_child_process_metadata(
        child_process_metadata_path,
        process_error_mode=process_error_mode,
        shared_root=(
            str(Path(args.shared_root).expanduser().resolve())
            if args.shared_root
            else None
        ),
    )
    print(
        f"[research-journey] pid={os.getpid()} "
        f"process_error_mode={process_error_mode}",
        flush=True,
    )

    if process_error_mode["requested"] and not process_error_mode["configured"]:
        error = "受控 child 的 Windows error dialog suppression 設定失敗；未載入 Qt"
        failure_payload = {
            "status": "failed",
            "evidence_kind": evidence_kind,
            "process_error_mode": process_error_mode,
            "run_dir": str(run_dir),
            "child_process_metadata": str(child_process_metadata_path),
            "error_type": "ProcessErrorModeConfigurationError",
            "error": error,
        }
        summary_path.write_text(
            json.dumps(failure_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _update_child_process_metadata(
            child_process_metadata_path,
            status="failed",
            ended_at=datetime.now().astimezone().isoformat(),
            exit_code=2,
        )
        print(f"Research journey Qt QA failed: {error}", file=sys.stderr)
        return 2

    try:
        if args.mode == "task_worker_lifecycle":
            evidence = _run_task_worker_lifecycle(run_dir)
        elif args.mode == "mainwindow_shutdown":
            evidence = _run_mainwindow_shutdown_lifecycle(run_dir)
        elif args.mode == "continuity_readback":
            if not args.shared_root:
                raise ValueError("continuity_readback 必須提供 --shared-root")
            evidence = _run_continuity_readback(
                run_dir,
                shared_root=Path(args.shared_root).expanduser().resolve(),
            )
        else:
            evidence = _run_journey(
                run_dir,
                shared_root=(
                    Path(args.shared_root).expanduser().resolve()
                    if args.shared_root
                    else None
                ),
            )
        payload: dict[str, Any] = {
            "status": "passed",
            "evidence_kind": evidence_kind,
            "mode": args.mode,
            "native_windows_interaction": "unavailable_without_cua_trusted_rpc",
            "screenreader": "not_tested",
            "process_error_mode": process_error_mode,
            "child_process_metadata": str(child_process_metadata_path),
            "shared_root": (
                str(Path(args.shared_root).expanduser().resolve())
                if args.shared_root
                else None
            ),
            "run_dir": str(run_dir),
            **evidence,
        }
        summary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _update_child_process_metadata(
            child_process_metadata_path,
            status="passed",
            ended_at=datetime.now().astimezone().isoformat(),
            exit_code=0,
        )
        print(f"Research journey Qt QA passed: {summary_path}")
        return 0
    except BaseException as exc:  # noqa: BLE001 - evidence must explain failure
        payload = {
            "status": "failed",
            "evidence_kind": evidence_kind,
            "mode": args.mode,
            "process_error_mode": process_error_mode,
            "child_process_metadata": str(child_process_metadata_path),
            "run_dir": str(run_dir),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        summary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _update_child_process_metadata(
            child_process_metadata_path,
            status="failed",
            ended_at=datetime.now().astimezone().isoformat(),
            exit_code=1,
        )
        print(f"Research journey Qt QA failed: {exc}", file=sys.stderr)
        return 1


def _configure_child_process_error_mode() -> dict[str, Any]:
    """僅在受控 QA 子程序內抑制 Windows 原生錯誤對話框。

    ``SetErrorMode`` 是 process-local API；這裡不修改 WER 設定、registry
    或其他程序。抑制 UI 不會把 native crash 轉成成功，wrapper 仍會保存
    子程序的實際非零退出碼與 log。
    """

    requested = os.environ.get("TECHNICAL_ANALYSIS_QA_CHILD") == "1"
    result: dict[str, Any] = {
        "requested": requested,
        "configured": False,
        "scope": "process",
        "flags": [],
    }
    if not requested:
        result["reason"] = "not_a_controlled_qa_child"
        return result
    if os.name != "nt":
        result["reason"] = "non_windows"
        return result

    sem_fail_critical_errors = 0x0001
    sem_no_gp_fault_error_box = 0x0002
    flags = sem_fail_critical_errors | sem_no_gp_fault_error_box
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        set_error_mode = kernel32.SetErrorMode
        set_error_mode.argtypes = [ctypes.c_uint]
        set_error_mode.restype = ctypes.c_uint
        previous = set_error_mode(flags)
        result.update(
            {
                "configured": True,
                "flags": [
                    "SEM_FAILCRITICALERRORS",
                    "SEM_NOGPFAULTERRORBOX",
                ],
                "previous_mode": f"0x{previous:08X}",
            }
        )
    except Exception as exc:  # noqa: BLE001 - preserve failure evidence
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _run_journey(
    output_dir: Path,
    *,
    shared_root: Path | None = None,
) -> dict[str, Any]:
    """Run one complete journey in a fresh isolated output directory.

    ``shared_root`` is used by the two-child continuity QA so the writer
    process can be replaced by a separately launched reader process.  When it
    is omitted, the historical per-run isolated root remains unchanged.
    """

    progress_path = output_dir / "progress.json"

    def mark_step(step: str, status: str = "completed", **details: Any) -> None:
        payload = {
            "run_dir": str(output_dir),
            "step": step,
            "status": status,
            "updated_at": datetime.now().isoformat(),
            **details,
        }
        progress_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[research-journey] {status}: {step}", flush=True)

    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # These must be set before importing Qt/MainWindow or TWStockConfig.
    isolated_root = shared_root or (output_dir / "isolated_app")
    isolated_root.mkdir(parents=True, exist_ok=True)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["DATA_ROOT"] = str(isolated_root / "data")
    os.environ["OUTPUT_ROOT"] = str(isolated_root / "output")
    os.environ["PROFILE"] = "prod"
    mark_step("environment_configured")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")
    from ui_qt.crash_diagnostics import (
        close_crash_diagnostics,
        install_crash_diagnostics,
    )

    crash_diagnostics_log_path = install_crash_diagnostics(
        isolated_root / "data"
    )
    print(
        f"[research-journey] crash_diagnostics_log={crash_diagnostics_log_path} "
        "native_trace=diagnostic_file; hang_trace=runner_stderr_log",
        flush=True,
    )
    faulthandler.dump_traceback_later(10.0, repeat=True)

    from PySide6.QtCore import QDateTime
    from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog

    from app_module.recommendation.contracts import ExecutionStatus
    from app_module.dtos.decision_continuity_dtos import (
        ACTION_NOTE,
        DecisionIdentity,
    )
    from app_module.saved_recommendation_queries import (
        build_recommendation_execution_queries,
    )
    from ui_qt.main import MainWindow, apply_app_theme
    from ui_qt.views.recommendation.execution_coordinator import (
        RecommendationExecutionRequest,
    )
    import ui_qt.widgets.decision_continuity_controls as continuity_controls_module

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication(sys.argv)
    apply_app_theme(app)

    dialog_patches = _install_non_blocking_message_boxes(QMessageBox)
    note_dialog_original = continuity_controls_module.QInputDialog.getMultiLineText
    save_dialog_original = QInputDialog.getText
    save_labels = iter(
        (
            "跨頁旅程推薦 A",
            "跨頁旅程推薦 B",
            "跨頁旅程推薦 A",
        )
    )

    def next_save_label(*args: Any, **kwargs: Any) -> tuple[str, bool]:
        del args, kwargs
        try:
            return next(save_labels), True
        except StopIteration as exc:
            raise AssertionError("Journey runner 出現未預期的保存名稱對話框") from exc

    setattr(QInputDialog, "getText", staticmethod(next_save_label))
    setattr(
        continuity_controls_module.QInputDialog,
        "getMultiLineText",
        staticmethod(lambda *args, **kwargs: ("跨頁研究筆記：保留原推薦來源", True)),
    )

    window: MainWindow | None = None
    restarted_window: MainWindow | None = None
    first_dialog: Any = None
    second_dialog: Any = None
    third_dialog: Any = None
    fourth_dialog: Any = None
    controller: Any = None
    original_apply: Any = None
    screenshots: list[str] = []

    try:
        window = MainWindow()
        mark_step("mainwindow_constructed")
        window.resize(1366, 768)
        window.show()
        app.processEvents()
        mark_step("mainwindow_shown")

        _assert(window.watchlist_service is not None, "MainWindow 未建立 watchlist service")

        # The normal app starts in legacy JSON mode in this fresh fixture.  Use
        # the real visible upgrade button so all subsequent watchlist writes go
        # through the canonical WatchlistRepository.
        window._select_main_workspace("watchlist")
        app.processEvents()
        watchlist = window.watchlist_view
        _assert(
            getattr(watchlist, "upgrade_storage_btn", None) is not None,
            "觀察清單缺少明確升級入口",
        )
        _assert(
            watchlist.upgrade_storage_btn.isVisible(),
            "隔離 fresh watchlist 未顯示升級入口",
        )
        watchlist.upgrade_storage_btn.click()
        app.processEvents()
        storage_status = window.watchlist_service.get_storage_status()
        _assert(storage_status.is_repository, "觀察清單未切換至 canonical SQLite writer")
        mark_step("watchlist_upgraded_to_canonical_repository")

        recommendation_view = window.recommendation_view
        window._select_main_workspace("recommendation")
        app.processEvents()
        result_a = _execute_and_save_recommendation(
            recommendation_view,
            window.config,
            app,
            result_id="journey-result-a",
            decision_date="2026-09-10",
            result_name="跨頁旅程推薦 A",
            top_n=2,
            execution_status_completed=ExecutionStatus.COMPLETED,
            execution_request_type=RecommendationExecutionRequest,
            query_builder=build_recommendation_execution_queries,
        )
        snapshot_a = _typed_universe_snapshot(result_a)
        mark_step(
            "recommendation_a_service_execution_saved_and_read_back",
            result_id=result_a.result_id,
            source_snapshot_id=snapshot_a.universe_snapshot_id,
            source_snapshot_hash=snapshot_a.universe_snapshot_hash,
        )
        _select_recommendation_row(recommendation_view, "2330")
        _assert(
            recommendation_view.stock_research_btn.isEnabled(),
            "推薦頁選取列後研究入口未啟用",
        )
        screenshots.append(_save_widget(recommendation_view, output_dir / "recommendation_surface.png"))

        # Recommendation -> watchlist uses the actual clicked signal and the
        # existing service writer.  Include a same-code second result to prove
        # candidate keys are not collapsed to stock_code only.
        recommendation_view.add_to_watchlist_btn.click()
        app.processEvents()
        mark_step("result_a_2330_added_to_watchlist")
        _select_recommendation_row(recommendation_view, "2317")
        recommendation_view.add_to_watchlist_btn.click()
        app.processEvents()
        mark_step("result_a_2317_added_to_watchlist")

        result_b = _execute_and_save_recommendation(
            recommendation_view,
            window.config,
            app,
            result_id="journey-result-b",
            decision_date="2026-09-11",
            result_name="跨頁旅程推薦 B",
            top_n=1,
            execution_status_completed=ExecutionStatus.COMPLETED,
            execution_request_type=RecommendationExecutionRequest,
            query_builder=build_recommendation_execution_queries,
        )
        snapshot_b = _typed_universe_snapshot(result_b)
        mark_step(
            "recommendation_b_service_execution_saved_and_read_back",
            result_id=result_b.result_id,
            source_snapshot_id=snapshot_b.universe_snapshot_id,
            source_snapshot_hash=snapshot_b.universe_snapshot_hash,
        )
        _select_recommendation_row(recommendation_view, "2330")
        recommendation_view.add_to_watchlist_btn.click()
        app.processEvents()
        mark_step("result_b_2330_added_to_watchlist")

        candidate_rows = window.watchlist_service.get_stocks()
        candidate_keys = _candidate_keys(candidate_rows, DecisionIdentity)
        expected_keys = [
            (result_a.result_id, "2330"),
            (result_a.result_id, "2317"),
            (result_b.result_id, "2330"),
        ]
        _assert(
            sorted(candidate_keys) == sorted(expected_keys),
            f"候選池 identity 不完整：{candidate_keys}",
        )
        _assert(
            len(candidate_rows) == 3,
            "同股不同推薦結果未保留為三筆獨立候選",
        )

        # Return to result A and open research via the real recommendation
        # button -> MainWindow stockResearchRequested connection.
        # 重新顯示 A 時仍走 typed finished callback 與正式保存按鈕；同一
        # sealed execution 的 create-only 保存會驗證既有 canonical bytes/readback。
        _apply_and_save_execution(
            recommendation_view,
            window.config,
            app,
            result_a,
            result_name="跨頁旅程推薦 A",
            execution_status_completed=ExecutionStatus.COMPLETED,
            query_builder=build_recommendation_execution_queries,
        )
        _select_recommendation_row(recommendation_view, "2330")
        recommendation_view.stock_research_btn.click()
        first_dialog = _wait_for_dialog(window, app)
        mark_step("recommendation_signal_opened_stock_research")
        first_journey, first_controls = _wait_for_loaded_journey(first_dialog, app)
        mark_step("first_journey_loaded")
        first_context = _current_context(window)
        _assert(first_context is not None, "推薦下鑽未寫入 session context")
        _assert(first_context.result_id == result_a.result_id, "推薦下鑽遺失 result_id")
        _assert(first_context.stock_code == "2330", "推薦下鑽遺失 stock_code")
        _assert(
            first_context.source_snapshot_id == snapshot_a.universe_snapshot_id,
            "推薦下鑽遺失 source_snapshot_id",
        )
        _assert(
            first_context.source_snapshot_hash == snapshot_a.universe_snapshot_hash,
            "推薦下鑽遺失 typed universe source_snapshot_hash",
        )
        controller = window.decision_continuity_controller
        first_identity = controller.identity_from_context(first_context)
        _assert(first_controls.identity == first_identity, "控制項 identity 與 session context 不一致")
        _assert(first_controls.state is not None and first_controls.state.can_write, "精確 candidate 尚不可寫")

        original_apply = controller.apply
        captured_requests: list[str] = []

        def capture_apply(action: str, identity: object, **kwargs: Any) -> Any:
            result = original_apply(action, identity, **kwargs)
            captured_requests.append(result.request_id)
            return result

        controller.apply = capture_apply  # type: ignore[method-assign]
        first_controls.accept_button.click()
        app.processEvents()
        _assert(first_controls.state is not None, "納入研究後沒有 state")
        _assert(first_controls.state.decision_status == "accepted", "納入研究未讀回 accepted")

        first_controls.note_button.click()
        app.processEvents()
        _assert(first_controls.state.active_note_count == 1, "筆記未保存或未讀回")
        note_request_id = captured_requests[-1] if captured_requests else ""
        _assert(bool(note_request_id), "筆記 action 未取得 request_id")
        history_before_redelivery = len(first_controls.state.history)
        redelivered = original_apply(
            ACTION_NOTE,
            first_identity,
            note="跨頁研究筆記：保留原推薦來源",
            request_id=note_request_id,
        )
        _assert(redelivered.success and redelivered.readback_verified, "同 request 重送未成功讀回")
        _assert(
            len(controller.read_state(first_identity).history) == history_before_redelivery,
            "同一 request id 重送新增了重複 journal revision",
        )

        first_controls.review_datetime.setDateTime(
            QDateTime.fromString("2026-09-20 10:30", "yyyy-MM-dd HH:mm")
        )
        first_controls.review_button.click()
        app.processEvents()
        _assert(first_controls.state is not None, "設定檢視後沒有 state")
        _assert(
            first_controls.state.next_review_at == "2026-09-20T10:30:00+08:00",
            f"下次檢視時間未正規化：{first_controls.state.next_review_at}",
        )
        _assert(
            len(first_controls.state.history) == 3,
            f"accept/note/review 應為三筆 append-only history：{len(first_controls.state.history)}",
        )
        mark_step("accept_note_review_persisted_and_readback_verified")

        # Reload through the real Journey widget callback to verify the same
        # exact candidate is read from the durable JournalService projection.
        first_journey.reload_button.click()
        _wait_for_loaded_journey(first_dialog, app)
        first_controls = first_dialog.journey_view.continuity_controls
        _assert(first_controls is not None and first_controls.state is not None, "Journey reload 無 continuity state")
        _assert(first_controls.state.decision_status == "accepted", "Journey reload 串到錯誤 decision")
        _assert(first_controls.state.active_note_count == 1, "Journey reload 遺失 note")
        _assert(
            first_controls.state.next_review_at == "2026-09-20T10:30:00+08:00",
            "Journey reload 遺失 review reminder",
        )
        _assert(
            len(first_controls.state.history) == 3,
            "Journey reload 產生或讀回錯誤 history 數量",
        )
        mark_step("journey_reload_readback_verified")
        first_dialog.report_tabs.setCurrentWidget(first_dialog.journey_view)
        app.processEvents()
        screenshots.append(_save_widget(first_dialog, output_dir / "decision_journey_after_write.png"))

        # The report's real return signal routes through MainWindow and restores
        # the exact recommendation row instead of returning to a guessed page.
        first_dialog.report_view.return_button.click()
        _assert(window is not None, "返回推薦頁時 MainWindow 不存在")
        current_window = window
        _wait_until(
            app,
            lambda: current_window.workspace_stack.currentWidget() is not current_window.stock_research_workspace,
            description="推薦研究視窗返回來源",
        )
        _assert(
            window.workspace_stack.currentWidget() is window.workspace_widgets["recommendation"],
            "研究報告返回未回到推薦頁",
        )
        selected = recommendation_view.results_table.selectionModel().selectedRows()
        _assert(len(selected) == 1 and selected[0].row() == 0, "返回推薦頁未定位 result A / 2330")
        mark_step("stock_research_returned_to_exact_recommendation_row")

        # Recommendation -> watchlist -> same recommendation / same stock.
        window._select_main_workspace("watchlist")
        app.processEvents()
        watchlist = window.watchlist_view
        _assert(watchlist.stocks_model is not None, "觀察清單 model 不存在")
        _assert(watchlist.stocks_model.rowCount() == 3, "觀察清單刷新後候選數量不一致")
        _assert(watchlist.select_stock("2330", result_a.result_id), "無法 exact 選取 result A / 2330")
        app.processEvents()
        _wait_until(
            app,
            lambda: result_a.result_id in watchlist.analysis_context_label.text()
            or result_a.result_id in watchlist.analysis_text.toPlainText(),
            description="觀察清單讀回 result A 摘要",
        )
        _assert(result_a.result_id in watchlist.analysis_context_label.text(), "觀察清單摘要未使用 exact result_id")
        screenshots.append(_save_widget(watchlist, output_dir / "watchlist_surface.png"))
        watchlist.stock_analysis_btn.click()
        second_dialog = _wait_for_dialog(window, app)
        mark_step("watchlist_opened_same_recommendation_same_stock")
        second_journey, second_controls = _wait_for_loaded_journey(second_dialog, app)
        second_context = _current_context(window)
        _assert(second_context is not None and second_context.result_id == result_a.result_id, "觀察清單下鑽錯誤 result_id")
        _assert(second_context.stock_code == "2330", "觀察清單下鑽錯誤 stock_code")
        _assert(
            second_context.source_snapshot_id == snapshot_a.universe_snapshot_id
            and second_context.source_snapshot_hash == snapshot_a.universe_snapshot_hash,
            "觀察清單下鑽未保留 result A typed universe identity",
        )
        _assert(second_controls.state is not None and second_controls.state.decision_status == "accepted", "同推薦同股未讀回 accepted")
        _assert(second_controls.state.active_note_count == 1, "同推薦同股未讀回 note")
        _assert(second_controls.state.next_review_at == "2026-09-20T10:30:00+08:00", "同推薦同股未讀回 reminder")
        _close_dialog(second_dialog, app)
        mark_step("same_recommendation_same_stock_readback_verified")

        # Same stock but result B must remain unrecorded.
        _assert(watchlist.select_stock("2330", result_b.result_id), "無法 exact 選取 result B / 2330")
        app.processEvents()
        watchlist.stock_analysis_btn.click()
        third_dialog = _wait_for_dialog(window, app)
        third_journey, third_controls = _wait_for_loaded_journey(third_dialog, app)
        third_context = _current_context(window)
        _assert(third_context is not None and third_context.result_id == result_b.result_id, "同股不同 result 串錯來源")
        _assert(third_context.stock_code == "2330", "同股不同 result 串錯股票")
        _assert(
            third_context.source_snapshot_id == snapshot_b.universe_snapshot_id
            and third_context.source_snapshot_hash == snapshot_b.universe_snapshot_hash,
            "同股不同 result 未保留 result B typed universe identity",
        )
        _assert(third_controls.state is not None and third_controls.state.decision_status == "unrecorded", "同股不同 result 錯誤繼承 decision")
        _assert(third_controls.state.active_note_count == 0, "同股不同 result 錯誤繼承 note")
        _assert(third_controls.state.next_review_at == "", "同股不同 result 錯誤繼承 reminder")
        _close_dialog(third_dialog, app)
        mark_step("same_stock_different_result_isolation_verified")

        # Same result but another stock gets an independent skipped decision.
        _assert(watchlist.select_stock("2317", result_a.result_id), "無法 exact 選取 result A / 2317")
        app.processEvents()
        watchlist.stock_analysis_btn.click()
        fourth_dialog = _wait_for_dialog(window, app)
        fourth_journey, fourth_controls = _wait_for_loaded_journey(fourth_dialog, app)
        fourth_context = _current_context(window)
        _assert(fourth_context is not None and fourth_context.result_id == result_a.result_id, "同 result 不同股串錯 result")
        _assert(fourth_context.stock_code == "2317", "同 result 不同股串錯 stock_code")
        _assert(
            fourth_context.source_snapshot_id == snapshot_a.universe_snapshot_id
            and fourth_context.source_snapshot_hash == snapshot_a.universe_snapshot_hash,
            "同 result 不同股未保留 result A typed universe identity",
        )
        fourth_controls.skip_button.click()
        app.processEvents()
        _assert(fourth_controls.state is not None and fourth_controls.state.decision_status == "skipped", "略過 action 未保存")
        _assert(fourth_controls.state.active_note_count == 0, "同 result 不同股錯誤繼承 note")
        _close_dialog(fourth_dialog, app)
        mark_step("same_result_different_stock_isolation_verified")

        # Open the actual Workbench workspace after the cross-page journey.
        window._select_main_workspace("workbench")
        app.processEvents()
        workbench = window.workbench_view
        _assert(
            window.workspace_stack.currentWidget() is workbench,
            "Workbench workspace 未由既有 navigation stack 顯示",
        )
        screenshots.append(_save_widget(workbench, output_dir / "workbench_surface.png"))
        mark_step("workbench_workspace_verified")

        _wait_for_managed_workers_idle(app)
        mark_step("background_workers_idle_before_restart")
        _close_main_window(window, app)
        window = None
        mark_step("first_mainwindow_closed")

        # Restart a fresh production MainWindow against the same isolated
        # paths.  This exercises discovery of the activated WatchlistRepository
        # and durable JournalService readback rather than an in-memory object.
        restarted_window = MainWindow()
        restarted_window.resize(1366, 768)
        restarted_window.show()
        app.processEvents()
        mark_step("restarted_mainwindow_constructed_and_shown")
        _assert(restarted_window.watchlist_service is not None, "重啟後 watchlist service 不存在")
        _assert(
            restarted_window.watchlist_storage_status.is_repository,
            "重啟後未發現已啟用 canonical watchlist repository",
        )
        restarted_window._select_main_workspace("watchlist")
        app.processEvents()
        restarted_watchlist = restarted_window.watchlist_view
        _assert(restarted_watchlist.stocks_model is not None, "重啟後 watchlist model 不存在")
        _assert(restarted_watchlist.stocks_model.rowCount() == 3, "重啟後候選池數量不一致")
        restarted_rows = restarted_window.watchlist_service.get_stocks()
        restarted_keys = _candidate_keys(restarted_rows, DecisionIdentity)
        _assert(sorted(restarted_keys) == sorted(expected_keys), "重啟後 typed candidate identity 不一致")
        _assert(restarted_watchlist.select_stock("2330", result_a.result_id), "重啟後無法 exact 選取 result A / 2330")
        app.processEvents()
        _wait_until(
            app,
            lambda: result_a.result_id in restarted_watchlist.analysis_context_label.text()
            or result_a.result_id in restarted_watchlist.analysis_text.toPlainText(),
            description="重啟後觀察清單讀回 result A 摘要",
        )
        screenshots.append(_save_widget(restarted_watchlist, output_dir / "watchlist_after_restart.png"))
        restarted_watchlist.stock_analysis_btn.click()
        restarted_dialog = _wait_for_dialog(restarted_window, app)
        restarted_journey, restarted_controls = _wait_for_loaded_journey(restarted_dialog, app)
        restarted_context = _current_context(restarted_window)
        _assert(restarted_context is not None, "重啟後研究 context 不存在")
        _assert(restarted_context.result_id == result_a.result_id, "重啟後 result_id 不一致")
        _assert(restarted_context.stock_code == "2330", "重啟後 stock_code 不一致")
        _assert(
            restarted_context.source_snapshot_id == snapshot_a.universe_snapshot_id
            and restarted_context.source_snapshot_hash == snapshot_a.universe_snapshot_hash,
            "重啟後未保留 result A typed universe identity",
        )
        _assert(restarted_controls.state is not None and restarted_controls.state.decision_status == "accepted", "重啟後未讀回 accepted")
        _assert(restarted_controls.state.active_note_count == 1, "重啟後未讀回 note")
        _assert(restarted_controls.state.next_review_at == "2026-09-20T10:30:00+08:00", "重啟後未讀回 reminder")
        mark_step("restart_watchlist_and_continuity_readback_verified")
        restarted_dialog.report_tabs.setCurrentWidget(restarted_dialog.journey_view)
        app.processEvents()
        screenshots.append(_save_widget(restarted_dialog, output_dir / "decision_journey_after_restart.png"))
        _close_dialog(restarted_dialog, app)
        restarted_dialog = None

        restarted_window._select_main_workspace("workbench")
        app.processEvents()
        _assert(
            restarted_window.workspace_stack.currentWidget() is restarted_window.workbench_view,
            "重啟後 Workbench workspace 未顯示",
        )
        screenshots.append(_save_widget(restarted_window.workbench_view, output_dir / "workbench_after_restart.png"))
        mark_step("restart_workbench_workspace_verified")

        _wait_for_managed_workers_idle(app)
        journal_path = Path(restarted_window.config.output_root) / "portfolio" / "journal_entries.jsonl"
        _assert(journal_path.is_file(), "append-only journal 未建立")
        revision_count = len(restarted_window.journal_service.list_decision_revisions())
        _assert(revision_count == 4, f"accept/note/review/skip 應為四筆 revision：{revision_count}")
        mark_step("journey_complete", revision_count=revision_count)

        return {
            "scope": {
                "component": [
                    "RecommendationService synthetic source provider and fixed Decimal scorer",
                    "RecommendationExecutionRequest, sealed execution, real UI save, and strict canonical query readback",
                    "RecommendationView production callback and stockResearchRequested signal",
                    "WatchlistService canonical WatchlistRepository writer",
                    "ResearchSessionStore typed context",
                    "DecisionContinuityController append-only JournalService",
                    "DecisionOutcomeJourneyWidget and MainWindow workspace navigation",
                ],
                "full_path": [
                    "recommendation -> StockResearch",
                    "accept / skip / note / review",
                    "return to recommendation",
                    "watchlist -> exact same recommendation / same stock",
                    "same stock different result and same result different stock isolation",
                    "Workbench",
                    "same-process MainWindow reconstruction -> watchlist -> "
                    "StockResearch -> Workbench",
                ],
                "real_data": (
                    "21-business-day synthetic market frames are cutoff at each request's "
                    "as-of date and scored by fixed Decimal facts through the real "
                    "RecommendationService. Typed universe snapshot identity is produced "
                    "by that execution and persisted through canonical UI save/readback; "
                    "no formal market, broker, Evidence, or live trading data is used."
                ),
            },
            "recommendation_execution": {
                "result_a": {
                    "result_id": result_a.result_id,
                    "selected_stock_codes": [item.stock_code for item in result_a.items],
                    "universe_snapshot_id": snapshot_a.universe_snapshot_id,
                    "universe_snapshot_hash": snapshot_a.universe_snapshot_hash,
                    "request_cutoff": "2026-09-10",
                },
                "result_b": {
                    "result_id": result_b.result_id,
                    "selected_stock_codes": [item.stock_code for item in result_b.items],
                    "universe_snapshot_id": snapshot_b.universe_snapshot_id,
                    "universe_snapshot_hash": snapshot_b.universe_snapshot_hash,
                    "request_cutoff": "2026-09-11",
                    "input_universe_codes": ["2317", "2330"],
                },
                "snapshot_hash_semantics": (
                    "canonical typed universe snapshot spec hash; not a digest of raw market rows"
                ),
            },
            "candidate_keys": [list(item) for item in sorted(candidate_keys)],
            "restart_candidate_keys": [list(item) for item in sorted(restarted_keys)],
            "restart_scope": "same_process_mainwindow_reconstruction_not_process_restart",
            "decision_states": {
                "journey-result-a/2330": {
                    "status": "accepted",
                    "active_note_count": 1,
                    "next_review_at": "2026-09-20T10:30:00+08:00",
                    "history_count": 3,
                },
                "journey-result-b/2330": {"status": "unrecorded"},
                "journey-result-a/2317": {"status": "skipped", "history_count": 1},
            },
            "watchlist_storage": {
                "mode_after_upgrade": storage_status.mode,
                "repository_path": str(storage_status.repository_path),
                "marker_exists_after_restart": WatchlistServiceMarker.exists_for(
                    restarted_window.watchlist_service
                ),
            },
            "journal": {
                "path": str(journal_path),
                "revision_count": revision_count,
                "idempotent_note_request_replayed": True,
            },
            "crash_diagnostics_log": str(crash_diagnostics_log_path),
            "screenshots": screenshots,
        }
    finally:
        print("[research-journey] teardown: dialogs:start", flush=True)
        if controller is not None and original_apply is not None:
            # The local wrapper is harmless in a short-lived QA process, but
            # restore it before closing so MainWindow teardown sees the real
            # controller method.
            try:
                controller.apply = original_apply  # type: ignore[method-assign]
            except (AttributeError, RuntimeError):
                pass
        if fourth_dialog is not None:
            _close_dialog(fourth_dialog, app)
            print("[research-journey] teardown: dialog_fourth:done", flush=True)
        if third_dialog is not None:
            _close_dialog(third_dialog, app)
            print("[research-journey] teardown: dialog_third:done", flush=True)
        if second_dialog is not None:
            _close_dialog(second_dialog, app)
            print("[research-journey] teardown: dialog_second:done", flush=True)
        if first_dialog is not None:
            _close_dialog(first_dialog, app)
            print("[research-journey] teardown: dialog_first:done", flush=True)
        if restarted_window is not None:
            _close_main_window(restarted_window, app)
            print("[research-journey] teardown: restarted_window:done", flush=True)
        if window is not None:
            _close_main_window(window, app)
            print("[research-journey] teardown: initial_window:done", flush=True)
        setattr(
            continuity_controls_module.QInputDialog,
            "getMultiLineText",
            note_dialog_original,
        )
        setattr(QInputDialog, "getText", save_dialog_original)
        print("[research-journey] teardown: dialog_patches_restore:start", flush=True)
        dialog_patches()
        print("[research-journey] teardown: dialog_patches_restore:done", flush=True)
        print("[research-journey] teardown: process_events:start", flush=True)
        app.processEvents()
        print("[research-journey] teardown: process_events:done", flush=True)
        app.quit()
        print("[research-journey] teardown: app_quit:done", flush=True)
        faulthandler.cancel_dump_traceback_later()
        print("[research-journey] teardown: faulthandler_cancelled", flush=True)
        close_crash_diagnostics()
        print("[research-journey] teardown: crash_diagnostics_closed", flush=True)


def _run_mainwindow_shutdown_lifecycle(output_dir: Path) -> dict[str, Any]:
    """Verify one-X shutdown on real production MainWindow instances.

    The busy case combines a real managed ``TaskWorker`` with a tiny external
    process that implements the same TPEX status/cancel-marker protocol.  The
    helper exits only after observing the marker and writing a
    ``cancel_completed`` receipt, so this checks the real MainWindow and
    UpdateView coordination without touching formal data or making a network
    request.
    """

    progress_path = output_dir / "progress.json"

    def mark_step(step: str, status: str = "completed", **details: Any) -> None:
        payload = {
            "run_dir": str(output_dir),
            "step": step,
            "status": status,
            "updated_at": datetime.now().isoformat(),
            **details,
        }
        progress_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[mainwindow-shutdown] {status}: {step}", flush=True)

    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    isolated_root = output_dir / "isolated_app"
    isolated_root.mkdir(parents=True, exist_ok=True)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["DATA_ROOT"] = str(isolated_root / "data")
    os.environ["OUTPUT_ROOT"] = str(isolated_root / "output")
    os.environ["PROFILE"] = "prod"
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")

    from ui_qt.crash_diagnostics import (
        close_crash_diagnostics,
        install_crash_diagnostics,
    )

    crash_log_path = install_crash_diagnostics(isolated_root / "data")
    faulthandler.dump_traceback_later(10.0, repeat=True)
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer

    from ui_qt.main import (
        MainWindow,
        _drain_qt_deferred_deletes,
        apply_app_theme,
    )
    from ui_qt.workers.task_worker import TaskWorker, running_task_workers

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication(sys.argv)
    apply_app_theme(app)

    idle_window: Any = None
    busy_window: Any = None
    busy_worker: Any = None
    tpex_process: Any = None
    tpex_cancel_file = output_dir / "tpex_shutdown_state.json.cancel"
    tpex_state_file = output_dir / "tpex_shutdown_state.json"
    busy_close_calls = 0
    busy_close_elapsed = 0.0
    natural_event_loop_returned = False

    def wait_for_no_managed_work(description: str, timeout_seconds: float = 12.0) -> None:
        _wait_until(
            app,
            lambda: not running_task_workers(),
            description=description,
            timeout_seconds=timeout_seconds,
        )

    try:
        mark_step("environment_configured", crash_diagnostics_log=str(crash_log_path))

        idle_window = MainWindow()
        idle_window.resize(1366, 768)
        idle_window.show()
        app.processEvents()
        mark_step("idle_mainwindow_shown")
        wait_for_no_managed_work("閒置驗收前的 production MainWindow worker")
        update_view = idle_window.update_view
        _assert(
            not update_view.has_running_background_process(),
            "閒置驗收前不應有 TPEX 背景程序",
        )
        mark_step("idle_precondition_verified")

        idle_close_started = time.monotonic()
        idle_window.close()
        idle_elapsed = time.monotonic() - idle_close_started
        _wait_until(
            app,
            lambda: not idle_window.isVisible(),
            description="閒置 MainWindow 第一次 close 後退出",
            timeout_seconds=5.0,
        )
        mark_step(
            "idle_first_close_accepted",
            close_calls=1,
            close_elapsed_seconds=idle_elapsed,
        )

        busy_window = MainWindow()
        busy_window.resize(1366, 768)
        busy_window.show()
        app.processEvents()
        wait_for_no_managed_work("忙碌驗收前的 production MainWindow 初始 worker")

        busy_update_view = busy_window.update_view
        tpex_cancel_file.unlink(missing_ok=True)
        tpex_state_file.write_text(
            json.dumps(
                {
                    "status": "running",
                    "mode": "qa_cooperative_shutdown",
                    "cancel_file": str(tpex_cancel_file),
                    "cancel_requested": False,
                    "cancel_completed": False,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        busy_update_view.tpex_refresh_state_file = tpex_state_file
        busy_update_view._tpex_cancel_file = tpex_cancel_file
        busy_update_view._tpex_cancel_requested = False
        busy_update_view._tpex_process_exit_code = None

        helper_code = (
            "import json,sys,time\n"
            "from pathlib import Path\n"
            "state=Path(sys.argv[1]); marker=Path(sys.argv[2])\n"
            "while not marker.exists(): time.sleep(0.01)\n"
            "try: payload=json.loads(state.read_text(encoding='utf-8'))\n"
            "except (OSError, json.JSONDecodeError): payload={}\n"
            "payload.update({'status':'cancelled','cancel_requested':True,"
            "'cancel_completed':True,'process_exit_code':0,"
            "'message':'QA helper observed cancel marker at safe boundary'})\n"
            "state.write_text(json.dumps(payload, ensure_ascii=False),"
            "encoding='utf-8')\n"
        )
        tpex_process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-c",
                helper_code,
                str(tpex_state_file),
                str(tpex_cancel_file),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=os.environ.copy(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        busy_update_view._tpex_background_process = tpex_process
        _assert(
            busy_update_view.has_running_background_process(),
            "忙碌驗收未建立可觀察的 TPEX 背景程序",
        )

        import threading

        worker_started = threading.Event()
        release_after_close = threading.Event()

        def cancellable_task(cancel_callback=None) -> str:
            worker_started.set()
            # Keep the dependency alive until the close event has returned, so
            # the evidence captures the required first-close ignored state
            # without relying on scheduler timing.
            while not release_after_close.is_set():
                time.sleep(0.01)
            while cancel_callback is None or not cancel_callback():
                time.sleep(0.01)
            return "cancelled-at-safe-boundary"

        busy_worker = TaskWorker(cancellable_task)
        busy_worker.start()
        _assert(worker_started.wait(5.0), "忙碌驗收 worker 未啟動")
        _assert(bool(running_task_workers()), "忙碌驗收未看到 managed worker")
        mark_step("busy_dependencies_started", tpex_pid=tpex_process.pid)

        def request_one_busy_close() -> None:
            nonlocal busy_close_calls, busy_close_elapsed
            busy_close_started = time.monotonic()
            busy_close_calls += 1
            busy_window.close()
            busy_close_elapsed = time.monotonic() - busy_close_started
            _assert(
                busy_window._shutdown_close_requested,
                "忙碌 MainWindow 第一次 close 未進入 shutdown coordinator",
            )
            _assert(
                busy_window.isVisible(),
                "忙碌 MainWindow 第一次 close 不應直接消失",
            )
            mark_step(
                "busy_first_close_requested",
                close_calls=busy_close_calls,
                close_elapsed_seconds=busy_close_elapsed,
                visible_after_first_close=True,
            )
            # Only after the close event has returned may the controlled task
            # reach its cancellation-safe boundary.
            release_after_close.set()

        _assert(
            app.quitOnLastWindowClosed(),
            "QApplication 未啟用 last-window 自然退出契約",
        )
        QTimer.singleShot(0, request_one_busy_close)
        app_exec_started = time.monotonic()
        app_exec_exit_code = app.exec()
        app_exec_elapsed = time.monotonic() - app_exec_started
        natural_event_loop_returned = True
        _assert(app_exec_exit_code == 0, f"QApplication.exec 非零返回：{app_exec_exit_code}")
        _assert(not busy_window.isVisible(), "QApplication.exec 返回時 busy MainWindow 仍可見")
        _assert(
            not running_task_workers(),
            "忙碌 MainWindow 自動關閉後仍有 managed worker",
        )
        _assert(
            busy_update_view._tpex_background_process is None,
            "TPEX process 已結束但 UpdateView 未完成觀察回收",
        )
        final_tpex_state = json.loads(tpex_state_file.read_text(encoding="utf-8"))
        _assert(final_tpex_state.get("status") == "cancelled", "TPEX 未寫入 cancelled receipt")
        _assert(
            final_tpex_state.get("cancel_completed") is True,
            "TPEX 缺少 cancel_completed receipt",
        )
        _assert(final_tpex_state.get("cancel_requested") is True, "TPEX 缺少 cancel_requested receipt")
        _assert(tpex_process.poll() == 0, "TPEX 合作式 helper 非零退出")
        mark_step(
            "busy_first_close_auto_completed",
            close_calls=busy_close_calls,
            app_exec_exit_code=app_exec_exit_code,
            app_exec_elapsed_seconds=app_exec_elapsed,
            tpex_exit_code=tpex_process.returncode,
            tpex_status=final_tpex_state.get("status"),
            tpex_cancel_completed=final_tpex_state.get("cancel_completed"),
        )

        return {
            "mode": "mainwindow_shutdown",
            "crash_diagnostics_log": str(crash_log_path),
            "idle": {
                "user_close_calls": 1,
                "first_close_auto_accepted": True,
                "close_elapsed_seconds": idle_elapsed,
            },
            "busy": {
                "user_close_calls": busy_close_calls,
                "first_close_ignored_then_auto_closed": True,
                "tpex_helper_pid": tpex_process.pid,
                "tpex_exit_code": tpex_process.returncode,
                "tpex_status": final_tpex_state.get("status"),
                "tpex_cancel_completed": final_tpex_state.get("cancel_completed"),
                "worker_cancelled_and_unregistered": True,
                "close_elapsed_seconds": busy_close_elapsed,
                "qapplication_exec_returned_naturally": natural_event_loop_returned,
                "qapplication_exec_exit_code": app_exec_exit_code,
                "qapplication_exec_elapsed_seconds": app_exec_elapsed,
            },
            "close_contract": (
                "idle and busy production MainWindow each received one user close; "
                "busy close auto-completed after worker and TPEX safe receipts"
            ),
        }
    finally:
        if busy_worker is not None:
            try:
                busy_worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                pass
            try:
                busy_worker.wait(5_000)
            except RuntimeError:
                pass
        if tpex_process is not None and tpex_process.poll() is None:
            try:
                tpex_cancel_file.parent.mkdir(parents=True, exist_ok=True)
                tpex_cancel_file.write_text("cleanup-requested", encoding="ascii")
                _wait_until(
                    app,
                    lambda: tpex_process.poll() is not None,
                    description="TPEX QA helper cooperative cleanup",
                    timeout_seconds=3.0,
                )
            except (OSError, AssertionError):
                # The owned launcher Job Object remains the final bounded
                # cleanup scope if a failed QA child cannot finish its helper.
                pass
        windows_to_delete = tuple(
            window for window in (busy_window, idle_window) if window is not None
        )
        for window in windows_to_delete:
            if window is None:
                continue
            try:
                if window.isVisible():
                    window.hide()
            except RuntimeError:
                pass
        app.processEvents()
        if not natural_event_loop_returned:
            app.quit()
        _drain_qt_deferred_deletes(app, windows_to_delete)
        faulthandler.cancel_dump_traceback_later()
        close_crash_diagnostics()


def _run_continuity_readback(
    output_dir: Path,
    *,
    shared_root: Path,
) -> dict[str, Any]:
    """Read continuity artifacts from a writer child in a fresh Qt process."""

    progress_path = output_dir / "progress.json"

    def mark_step(step: str, status: str = "completed", **details: Any) -> None:
        payload = {
            "run_dir": str(output_dir),
            "shared_root": str(shared_root),
            "step": step,
            "status": status,
            "updated_at": datetime.now().isoformat(),
            **details,
        }
        progress_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[continuity-readback] {status}: {step}", flush=True)

    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    shared_root = shared_root.expanduser().resolve()
    if not (shared_root / "data").is_dir() or not (shared_root / "output").is_dir():
        raise AssertionError(f"writer child 的 shared root 不完整：{shared_root}")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["DATA_ROOT"] = str(shared_root / "data")
    os.environ["OUTPUT_ROOT"] = str(shared_root / "output")
    os.environ["PROFILE"] = "prod"
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")

    from ui_qt.crash_diagnostics import (
        close_crash_diagnostics,
        install_crash_diagnostics,
    )

    crash_log_path = install_crash_diagnostics(shared_root / "data")
    faulthandler.dump_traceback_later(10.0, repeat=True)
    from PySide6.QtWidgets import QApplication

    from app_module.dtos.decision_continuity_dtos import DecisionIdentity
    from ui_qt.main import MainWindow, apply_app_theme
    from ui_qt.workers.task_worker import running_task_workers

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication(sys.argv)
    apply_app_theme(app)
    window: Any = None
    dialog: Any = None
    try:
        mark_step("environment_configured", crash_diagnostics_log=str(crash_log_path))
        window = MainWindow()
        window.resize(1366, 768)
        window.show()
        app.processEvents()
        mark_step("reader_mainwindow_constructed_and_shown", reader_pid=os.getpid())
        _assert(window.watchlist_service is not None, "reader child watchlist service 不存在")
        _assert(
            window.watchlist_storage_status.is_repository,
            "reader child 未發現 writer child 啟用的 canonical repository",
        )

        expected_keys = sorted(
            [
                ("journey-result-a", "2330"),
                ("journey-result-a", "2317"),
                ("journey-result-b", "2330"),
            ]
        )
        rows = window.watchlist_service.get_stocks()
        actual_keys = sorted(_candidate_keys(rows, DecisionIdentity))
        _assert(actual_keys == expected_keys, f"獨立 reader child candidate identity 不一致：{actual_keys}")
        mark_step(
            "independent_child_candidate_identity_readback_verified",
            candidate_keys=[list(item) for item in actual_keys],
        )

        window._select_main_workspace("watchlist")
        app.processEvents()
        watchlist = window.watchlist_view
        _assert(watchlist.stocks_model is not None, "reader child watchlist model 不存在")
        _assert(watchlist.select_stock("2330", "journey-result-a"), "reader child 無法 exact 選取 result A / 2330")
        app.processEvents()
        _wait_until(
            app,
            lambda: "journey-result-a" in watchlist.analysis_context_label.text()
            or "journey-result-a" in watchlist.analysis_text.toPlainText(),
            description="reader child 讀回 exact result A 摘要",
        )
        _assert(
            "journey-result-a" in watchlist.analysis_context_label.text(),
            "reader child 摘要未保留 exact result_id",
        )
        watchlist.stock_analysis_btn.click()
        dialog = _wait_for_dialog(window, app)
        _journey, controls = _wait_for_loaded_journey(dialog, app)
        context = _current_context(window)
        _assert(context is not None, "reader child 研究 context 不存在")
        _assert(context.result_id == "journey-result-a", "reader child result_id 不一致")
        _assert(context.stock_code == "2330", "reader child stock_code 不一致")
        _assert(controls.state is not None, "reader child continuity state 不存在")
        _assert(controls.state.decision_status == "accepted", "reader child 未讀回 accepted")
        _assert(controls.state.active_note_count == 1, "reader child 未讀回 note")
        _assert(
            controls.state.next_review_at == "2026-09-20T10:30:00+08:00",
            "reader child 未讀回 reminder",
        )
        _assert(len(controls.state.history) == 3, "reader child history revision 數量不一致")
        mark_step(
            "independent_child_continuity_state_readback_verified",
            result_id=context.result_id,
            stock_code=context.stock_code,
            decision_status=controls.state.decision_status,
            active_note_count=controls.state.active_note_count,
            next_review_at=controls.state.next_review_at,
            history_count=len(controls.state.history),
        )
        _close_dialog(dialog, app)
        dialog = None
        window._select_main_workspace("workbench")
        app.processEvents()
        _assert(
            window.workspace_stack.currentWidget() is window.workbench_view,
            "reader child Workbench workspace 未顯示",
        )
        revision_count = len(window.journal_service.list_decision_revisions())
        _assert(revision_count == 4, f"reader child journal revision 不一致：{revision_count}")
        mark_step("independent_child_workbench_and_journal_verified", revision_count=revision_count)

        return {
            "mode": "continuity_readback",
            "cross_process": True,
            "writer_child_is_not_this_process": True,
            "reader_pid": os.getpid(),
            "shared_root": str(shared_root),
            "candidate_keys": [list(item) for item in actual_keys],
            "continuity": {
                "result_id": "journey-result-a",
                "stock_code": "2330",
                "decision_status": "accepted",
                "active_note_count": 1,
                "next_review_at": "2026-09-20T10:30:00+08:00",
                "history_count": 3,
            },
            "journal_revision_count": revision_count,
            "crash_diagnostics_log": str(crash_log_path),
        }
    finally:
        _close_dialog(dialog, app)
        if window is not None:
            try:
                _wait_for_managed_workers_idle(app)
            except AssertionError:
                pass
            _close_main_window(window, app)
        app.processEvents()
        app.quit()
        faulthandler.cancel_dump_traceback_later()
        close_crash_diagnostics()


def _run_task_worker_lifecycle(output_dir: Path) -> dict[str, Any]:
    """最小 Qt child：驗證 worker 重用、完成清理與 deleted wrapper 防禦。"""

    progress_path = output_dir / "progress.json"

    def mark_step(step: str, status: str = "completed", **details: Any) -> None:
        payload = {
            "run_dir": str(output_dir),
            "step": step,
            "status": status,
            "updated_at": datetime.now().isoformat(),
            **details,
        }
        progress_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[task-worker-lifecycle] {status}: {step}", flush=True)

    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    isolated_root = output_dir / "isolated_app"
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["DATA_ROOT"] = str(isolated_root / "data")
    os.environ["OUTPUT_ROOT"] = str(isolated_root / "output")
    os.environ["PROFILE"] = "prod"
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")

    from ui_qt.crash_diagnostics import (
        close_crash_diagnostics,
        install_crash_diagnostics,
    )

    crash_log_path = install_crash_diagnostics(isolated_root / "data")
    faulthandler.dump_traceback_later(10.0, repeat=True)
    from PySide6.QtWidgets import QApplication

    from ui_qt.workers.task_worker import (
        TaskWorker,
        running_task_workers,
    )
    import ui_qt.workers.task_worker as task_worker_module

    import shiboken6
    import threading

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication(sys.argv)

    first_started = threading.Event()
    first_release = threading.Event()
    second_started = threading.Event()
    second_release = threading.Event()
    run_count = 0
    worker: Any = None

    def task() -> str:
        nonlocal run_count
        run_count += 1
        if run_count == 1:
            first_started.set()
            first_release.wait(5.0)
            return "first"
        second_started.set()
        second_release.wait(5.0)
        return "second"

    try:
        mark_step("environment_configured")
        worker = TaskWorker(task)
        worker.start()
        _assert(first_started.wait(5.0), "第一輪 worker 未啟動")
        _assert(worker in running_task_workers(), "第一輪 worker 未被 shutdown probe 看到")
        mark_step("first_worker_registered")

        first_release.set()
        _assert(worker.wait(5_000), "第一輪 worker 未在 bounded wait 內結束")
        app.processEvents()
        _wait_until(
            app,
            lambda: worker not in running_task_workers(),
            description="第一輪 native finished registry cleanup",
        )
        mark_step("first_worker_finished_and_unregistered")

        worker.start()
        _assert(second_started.wait(5.0), "重用 worker 未啟動")
        _assert(worker in running_task_workers(), "重用 worker 未恢復 managed registry")
        mark_step("reused_worker_registered")

        second_release.set()
        _assert(worker.wait(5_000), "重用 worker 未在 bounded wait 內結束")
        app.processEvents()
        _wait_until(
            app,
            lambda: worker not in running_task_workers(),
            description="重用 worker native finished registry cleanup",
        )
        mark_step("reused_worker_finished_and_unregistered")

        deleted_worker = TaskWorker(lambda: None)
        _assert(
            deleted_worker in task_worker_module._MANAGED_TASK_WORKERS,
            "deleted-wrapper fixture 未進入 managed registry",
        )
        shiboken6.delete(deleted_worker)
        _assert(running_task_workers() == (), "deleted C++ wrapper 未被 shutdown probe 丟棄")
        mark_step("deleted_cpp_wrapper_discarded")
        return {
            "mode": "task_worker_lifecycle",
            "crash_diagnostics_log": str(crash_log_path),
            "worker_reuse_verified": True,
            "deleted_cpp_wrapper_probe_verified": True,
        }
    finally:
        first_release.set()
        second_release.set()
        if worker is not None:
            try:
                worker.wait(5_000)
            except RuntimeError:
                pass
            app.processEvents()
            try:
                worker.deleteLater()
            except RuntimeError:
                pass
        app.processEvents()
        app.quit()
        faulthandler.cancel_dump_traceback_later()
        close_crash_diagnostics()


_RESEARCH_JOURNEY_SCORE_FACTS: dict[
    str, dict[str, tuple[Decimal, Decimal, Decimal, Decimal]]
] = {
    "journey-result-a": {
        "2330": (Decimal("88.00"), Decimal("28.00"), Decimal("30.00"), Decimal("30.00")),
        "2317": (Decimal("77.00"), Decimal("17.00"), Decimal("30.00"), Decimal("30.00")),
    },
    "journey-result-b": {
        "2330": (Decimal("66.00"), Decimal("16.00"), Decimal("25.00"), Decimal("25.00")),
        "2317": (Decimal("55.00"), Decimal("15.00"), Decimal("20.00"), Decimal("20.00")),
    },
}


class _ResearchJourneyRecommendationMarketFrameProvider:
    """提供截止各次 request 日期的隔離雙股票市場 frame。"""

    def __init__(self, as_of_date: str) -> None:
        self.as_of_date = as_of_date

    def __call__(self) -> Any:
        import pandas as pd

        trading_days = pd.bdate_range(end=pd.Timestamp(self.as_of_date), periods=21)
        rows: list[dict[str, Any]] = []
        for instrument_index, (stock_code, stock_name) in enumerate(
            (("2330", "台積電"), ("2317", "鴻海"))
        ):
            for day_index, day in enumerate(trading_days):
                rows.append(
                    {
                        "日期": day,
                        "available_date": day,
                        "證券代號": stock_code,
                        "證券名稱": stock_name,
                        "收盤價": Decimal("1000.00")
                        + Decimal(instrument_index)
                        + Decimal(day_index),
                        "成交股數": 1_000_000 + instrument_index + day_index,
                        "漲幅%": Decimal("1.20"),
                        "成交量變化率%": Decimal("5.00"),
                    }
                )
        return pd.DataFrame(rows)


def _score_research_journey_candidate(stock_df: Any, config: dict[str, Any]) -> Any:
    """以固定 Decimal 輸出隔離 scorer facts，不在 fixture 執行裸 float 計算。"""

    import pandas as pd

    result_id = str(config.get("result_id") or "")
    stock_code = str(stock_df.iloc[-1]["證券代號"])
    try:
        total_score, indicator_score, pattern_score, volume_score = (
            _RESEARCH_JOURNEY_SCORE_FACTS[result_id][stock_code]
        )
    except KeyError as exc:
        raise AssertionError(
            f"推薦 scorer 收到未列入 Journey fixture 的 identity：{result_id}/{stock_code}"
        ) from exc
    return pd.DataFrame(
        {
            "FinalScore": [total_score],
            "TotalScore": [total_score],
            "收盤價": [Decimal("1000.00")],
            "成交股數": [1_000_000],
            "IndicatorScore": [indicator_score],
            "PatternScore": [pattern_score],
            "VolumeScore": [volume_score],
        }
    )


def _typed_universe_snapshot(execution: Any) -> Any:
    identity = execution.context.universe_identity
    snapshot = identity.snapshot if identity is not None else None
    _assert(snapshot is not None, "sealed execution 缺少 typed universe snapshot")
    _assert(
        bool(snapshot.universe_snapshot_id and snapshot.universe_snapshot_hash),
        "typed universe snapshot 缺少 canonical identity/hash",
    )
    return snapshot


def _execute_and_save_recommendation(
    view: Any,
    config: Any,
    app: Any,
    *,
    result_id: str,
    decision_date: str,
    result_name: str,
    top_n: int,
    execution_status_completed: Any,
    execution_request_type: Any,
    query_builder: Any,
) -> Any:
    """走真 RecommendationService、sealed request、UI 保存與 canonical 查回。"""

    from pathlib import Path

    service = view.recommendation_service
    provider = _ResearchJourneyRecommendationMarketFrameProvider(decision_date)
    service.market_data_provider = provider
    service.industry_mapper.get_stock_industries = lambda _stock_code: []
    service.strategy_configurator.generate_recommendations = (
        _score_research_journey_candidate
    )
    request_config = {
        "result_id": result_id,
        "as_of_date": decision_date,
        "decision_date": decision_date,
        "data_date": decision_date,
        "source_id": type(provider).__name__,
        "source_kind": "synthetic_research_fixture",
        "profile_id": "research-journey-fixture",
        "profile_version": "fixture-v1",
        "strategy_version_id": "research-journey-strategy-v1",
        "strategy_config_id": "research-journey-config-v1",
        "regime": "Trend",
        "recommendation_ranking": {"threshold_mode": "fixed"},
    }
    request = execution_request_type(request_config, max_stocks=2, top_n=top_n)
    execution = request.execute(service)
    _assert(
        execution.status is execution_status_completed,
        f"RecommendationService 未產生 completed execution：{execution.status.value}",
    )
    expected_scores = _RESEARCH_JOURNEY_SCORE_FACTS[result_id]
    expected_codes = (
        ("2330", "2317") if top_n == 2 else ("2330",)
    )
    _assert(
        tuple(item.stock_code for item in execution.items) == expected_codes,
        f"真 Service 的 rank/top-N 與受控 scorer 不符："
        f"{tuple(item.stock_code for item in execution.items)}",
    )
    for item in execution.items:
        expected_score = expected_scores[item.stock_code][0]
        _assert(
            type(item.rule_score) is Decimal and item.rule_score == expected_score,
            f"{result_id}/{item.stock_code} rule_score 未保留固定 Decimal scorer fact",
        )

    snapshot = _typed_universe_snapshot(execution)
    snapshot_spec = json.loads(snapshot.universe_snapshot_spec_json)
    _assert(
        snapshot_spec["selected_codes"] == ["2317", "2330"]
        and snapshot_spec["selected_count"] == 2,
        "typed input-universe 必須保留兩股，即使 B 的 top-N 只選一股",
    )
    _assert(
        snapshot_spec["decision_date"] == decision_date
        and snapshot_spec["source_provider_id"] == type(provider).__name__,
        "typed universe snapshot 必須與本次 provider/request 截止日一致",
    )
    _assert(
        snapshot.universe_snapshot_source_provider_id == type(provider).__name__,
        "typed universe snapshot source provider 與實際 provider 不一致",
    )

    _apply_and_save_execution(
        view,
        config,
        app,
        execution,
        result_name=result_name,
        execution_status_completed=execution_status_completed,
        query_builder=query_builder,
    )
    # 新 query 物件從同一隔離 config 讀取已保存 execution，不復用 DTO 或 UI latest state。
    read_model = query_builder(config).get(result_id)
    _assert(read_model is not None, f"canonical query 未讀回 {result_id}")
    _assert(
        read_model.execution == execution
        and read_model.integrity_basis == "canonical_payload_and_index_verified",
        f"canonical readback 與本次 sealed execution 不一致：{result_id}",
    )
    legacy_result_path = (
        Path(config.output_root)
        / "recommendation"
        / "runs"
        / f"{result_id}.json"
    )
    _assert(
        not legacy_result_path.exists(),
        f"canonical writer 不應另寫 legacy JSON：{legacy_result_path}",
    )
    return execution


def _apply_and_save_execution(
    view: Any,
    config: Any,
    app: Any,
    execution: Any,
    *,
    result_name: str,
    execution_status_completed: Any,
    query_builder: Any,
) -> None:
    """以正式 typed callback 與保存控制項建立或確認 canonical readback。"""

    view._on_recommendation_finished(execution)
    app.processEvents()
    _assert(
        view.current_execution is execution
        and execution.status is execution_status_completed,
        "RecommendationView 未套用同一個 completed sealed execution",
    )
    _assert(not view.current_result_id, "未保存 execution 不應預先帶有 result_id")
    _assert(view.save_result_btn.isVisible(), "completed execution 未顯示正式保存入口")
    view.results_table.selectRow(0)
    app.processEvents()
    view.save_result_btn.click()
    app.processEvents()

    receipt = view.current_save_receipt
    _assert(receipt is not None, "正式保存按鈕未建立 SaveReceipt")
    _assert(
        receipt.result_id == execution.result_id
        and getattr(receipt.index_status, "value", None) == "indexed",
        "正式保存未取得同一 execution 的 INDEXED receipt",
    )
    _assert(
        view.current_result_id == execution.result_id
        and view._verified_saved_result_id() == execution.result_id,
        "推薦頁 result_id 必須來自 verified canonical UI save readback",
    )
    saved = query_builder(config).get(execution.result_id)
    _assert(saved is not None, "保存後新的 canonical query 未讀回 execution")
    _assert(
        saved.execution == execution
        and saved.result_id == execution.result_id
        and saved.integrity_basis == "canonical_payload_and_index_verified"
        and saved.label == result_name
        and saved.payload_hash == receipt.payload_hash
        and saved.artifact_location == receipt.artifact_location
        and saved.persisted_at == receipt.persisted_at,
        "UI save receipt 與新的 canonical query readback 不一致",
    )


def _select_recommendation_row(view: Any, stock_code: str) -> None:
    _assert(
        view._verified_saved_result_id() == view.current_result_id,
        "推薦列定位前必須持有同一 verified canonical saved identity",
    )
    _assert(view.select_stock(stock_code, view.current_result_id), f"推薦頁無法選取 {stock_code}")
    _assert(
        view.results_table.selectionModel().selectedRows(),
        f"推薦頁選取 {stock_code} 後沒有 selected row",
    )


def _candidate_keys(rows: list[dict[str, Any]], identity_type: Any) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for row in rows:
        identity = identity_type.from_mapping(
            row.get("decision_identity", {}),
            default_stock_code=str(row.get("stock_code", "")),
        )
        values.append(identity.candidate_key or ("", str(row.get("stock_code", ""))))
    return values


def _current_context(window: Any) -> Any:
    snapshot = window.research_session_store.get_snapshot()
    return snapshot.stock_context


def _wait_for_dialog(window: Any, app: Any) -> Any:
    _wait_until(
        app,
        lambda: getattr(window, "stock_research_workspace", None) is not None,
        description="MainWindow 建立個股研究視窗",
    )
    dialog = window.stock_research_workspace
    _assert(dialog is not None, "個股研究視窗不存在")
    _wait_until(app, lambda: bool(dialog.isVisible()), description="個股研究視窗顯示")
    return dialog


def _wait_for_loaded_journey(dialog: Any, app: Any) -> tuple[Any, Any]:
    _wait_until(
        app,
        lambda: getattr(dialog, "journey_view", None) is not None
        and dialog.journey_view.journey is not None,
        description="Journey exact result 載入",
        timeout_seconds=12.0,
    )
    journey = dialog.journey_view
    _assert(journey is not None, "Journey widget 不存在")
    _wait_until(app, lambda: not dialog.is_busy(), description="研究報告與 Journey 背景工作完成")
    controls = journey.continuity_controls
    _assert(controls is not None, "Journey 缺少 continuity controls")
    return journey, controls


def _wait_until(
    app: Any,
    predicate: Callable[[], bool],
    *,
    description: str,
    timeout_seconds: float = 8.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        from PySide6.QtTest import QTest

        QTest.qWait(20)
    raise AssertionError(f"等待逾時：{description}")


def _wait_for_managed_workers_idle(app: Any) -> None:
    """在 closeEvent 前等 native QThread.finished，避免查詢活躍 thread。"""

    import ui_qt.workers.task_worker as task_worker_module

    _wait_until(
        app,
        lambda: not task_worker_module._LIVE_TASK_WORKERS,
        description="受管 Qt 背景工作安全完成",
        timeout_seconds=8.0,
    )


def _close_dialog(dialog: Any, app: Any) -> None:
    if dialog is None:
        return
    try:
        if dialog.isVisible():
            from ui_qt.views.stock_research_workspace import StockResearchWorkspace
            if isinstance(dialog, StockResearchWorkspace):
                dialog.window()._select_main_workspace("workbench")
            else:
                dialog.close()
        _wait_until(app, lambda: not dialog.isVisible(), description="個股研究視窗安全關閉", timeout_seconds=8.0)
    except (RuntimeError, AssertionError):
        # Teardown is best effort after an assertion; the main failure remains
        # the evidence assertion rather than a second close-time exception.
        try:
            dialog.hide()
        except RuntimeError:
            pass
    app.processEvents()


def _close_main_window(window: Any, app: Any) -> None:
    if window is None:
        return
    print("[research-journey] teardown: close_main_window:start", flush=True)
    try:
        for attempt in range(5):
            if not window.isVisible():
                print(
                    f"[research-journey] teardown: already_hidden:{attempt}",
                    flush=True,
                )
                break
            print(
                f"[research-journey] teardown: close_attempt:{attempt}",
                flush=True,
            )
            window.close()
            print(
                f"[research-journey] teardown: close_returned:{attempt}",
                flush=True,
            )
            app.processEvents()
            print(
                f"[research-journey] teardown: events_processed:{attempt}",
                flush=True,
            )
            if not window.isVisible():
                break
            from PySide6.QtTest import QTest

            QTest.qWait(50)
        if window.isVisible():
            window.hide()
            print("[research-journey] teardown: forced_hide", flush=True)
    except RuntimeError:
        pass
    app.processEvents()
    print("[research-journey] teardown: close_main_window:done", flush=True)


def _save_widget(widget: Any, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    pixmap = widget.grab()
    _assert(not pixmap.isNull(), f"Qt screenshot 無效：{path}")
    _assert(pixmap.save(str(path)), f"Qt screenshot 保存失敗：{path}")
    return str(path)


def _install_non_blocking_message_boxes(message_box_type: Any) -> Callable[[], None]:
    originals: dict[str, Any] = {}

    def _ok(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return message_box_type.Ok

    def _yes(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return message_box_type.Yes

    for name, callback in (
        ("information", _ok),
        ("warning", _ok),
        ("critical", _ok),
        ("question", _yes),
    ):
        originals[name] = getattr(message_box_type, name)
        setattr(message_box_type, name, staticmethod(callback))

    def restore() -> None:
        for name, original in originals.items():
            setattr(message_box_type, name, original)

    return restore


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class WatchlistServiceMarker:
    """Small evidence-only adapter avoiding a second repository construction."""

    @staticmethod
    def exists_for(service: Any) -> bool:
        path = getattr(service, "canonical_repository_path", None)
        marker = getattr(service, "activation_marker_path", None)
        if path is None or not callable(marker):
            return False
        return marker(path).is_file()


if __name__ == "__main__":
    raise SystemExit(main())
