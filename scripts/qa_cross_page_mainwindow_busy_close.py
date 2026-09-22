"""Standalone actual MainWindow busy-close probe for the cross-page journey."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_service import StockResearchReportReadService
from ui_qt.main import (
    MainWindow,
    _configure_console_streams,
    _drain_qt_deferred_deletes,
)

_configure_console_streams()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--receipt", required=True)
    return parser.parse_args()


class _ProbeMainWindow(MainWindow):
    """Keep the production MainWindow lifecycle while exposing close evidence."""

    def __init__(self) -> None:
        super().__init__()
        self.close_event_count = 0

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.close_event_count += 1
        super().closeEvent(event)


def main() -> int:
    args = _parse_args()
    data_root = Path(args.data_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    receipt_path = Path(args.receipt).expanduser().resolve()
    os.environ["DATA_ROOT"] = str(data_root)
    os.environ["OUTPUT_ROOT"] = str(output_root)

    receipt: dict[str, object] = {
        "pid": os.getpid(),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "actual_main_window": False,
        "research_workers_finished": False,
        "report_worker_reached_busy_barrier": False,
        "close_requested_while_busy": False,
        "user_close_requests": 0,
        "main_window_close_event_count": 0,
        "forced_termination": False,
        "watchdog_fired": False,
        "app_exec_returncode": None,
        "process_exit_code": 1,
    }
    window: _ProbeMainWindow | None = None
    release_worker = Event()
    worker_started = Event()

    try:
        app = QApplication.instance() or QApplication(sys.argv)
        window = _ProbeMainWindow()
        receipt["actual_main_window"] = isinstance(window, MainWindow)
        report_service = StockResearchReportReadService(window.config)

        class BarrierReportReadService:
            def read_report(
                self,
                stock_code: str,
                *,
                context=None,
                cancel_callback=None,
            ):
                del cancel_callback
                worker_started.set()
                receipt["report_worker_reached_busy_barrier"] = True
                if not release_worker.wait(timeout=10):
                    raise TimeoutError("MainWindow busy-close worker release timed out")
                return report_service.read_report(stock_code, context=context)

        window.stock_research_report_service = BarrierReportReadService()
        window.stock_research_workspace.report_view.service = window.stock_research_report_service
        context = ResearchStockContextDTO(
            stock_code="2330",
            stock_name="台積電",
            result_id="busy-close-fixture",
            decision_date="2026-09-10",
            data_date="2026-09-10",
            identity_status="linked",
            source_snapshot_id="snap-busy-close",
            source_snapshot_hash="hash-busy-close",
            source_id="synthetic.busy_close_fixture",
            source_kind="synthetic_research_fixture",
            source_workspace="portfolio",
        )
        window._open_stock_research_context(context)

        def mark_research_workers_finished() -> None:
            receipt["research_workers_finished"] = not dialog.is_busy()

        dialog = window.stock_research_workspace
        if dialog is None:
            raise RuntimeError("MainWindow did not create StockResearchWorkspace")
        app.aboutToQuit.connect(mark_research_workers_finished)

        close_deadline = time.monotonic() + 10

        def request_one_user_close() -> None:
            active_dialog = window.stock_research_workspace
            if not worker_started.is_set() or active_dialog is None or not active_dialog.is_busy():
                if time.monotonic() >= close_deadline:
                    receipt["error"] = "report worker did not reach a busy dialog"
                    release_worker.set()
                    window.close()
                    return
                QTimer.singleShot(10, request_one_user_close)
                return
            receipt["close_requested_while_busy"] = True
            receipt["user_close_requests"] = int(receipt["user_close_requests"]) + 1
            window.close()
            # The close path has already requested cooperative cancellation;
            # release the deterministic probe only after that user request.
            release_worker.set()

        window.show()
        QTimer.singleShot(0, request_one_user_close)

        def watchdog() -> None:
            receipt["watchdog_fired"] = True
            app.quit()

        QTimer.singleShot(15_000, watchdog)
        app_exec_returncode = int(app.exec())
        receipt["app_exec_returncode"] = app_exec_returncode
        receipt["main_window_close_event_count"] = window.close_event_count
        receipt["main_window_hidden_after_exec"] = not window.isVisible()
        receipt["process_exit_code"] = int(
            0
            if receipt["actual_main_window"] is True
            and receipt["research_workers_finished"] is True
            and receipt["report_worker_reached_busy_barrier"] is True
            and receipt["close_requested_while_busy"] is True
            and receipt["user_close_requests"] == 1
            and receipt["forced_termination"] is False
            and receipt["watchdog_fired"] is False
            and app_exec_returncode == 0
            else 1
        )
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        release_worker.set()
        app = QApplication.instance()
        if app is not None and window is not None:
            try:
                _drain_qt_deferred_deletes(app, (window,))
            except (RuntimeError, TypeError):
                pass
        receipt["main_window_close_event_count"] = (
            window.close_event_count if window is not None else 0
        )
        receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return int(receipt["process_exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
