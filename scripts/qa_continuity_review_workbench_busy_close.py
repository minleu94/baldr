"""Standalone Qt close-path probe for the continuity Workbench integration."""

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

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.decision_continuity_controller import DecisionContinuityController
from app_module.decision_outcome_journey import DecisionOutcomeJourneyService
from app_module.journal_service import JournalService
from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_service import StockResearchReportReadService
from data_module.config import TWStockConfig
from ui_qt.views.stock_research_report_view import StockResearchReportDialog


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--db-file", required=True)
    parser.add_argument("--result-id", required=True)
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--receipt", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    receipt_path = Path(args.receipt).expanduser().resolve()
    started_at = datetime.now(timezone.utc).isoformat()
    receipt: dict[str, object] = {
        "pid": os.getpid(),
        "started_at_utc": started_at,
        "close_requested_while_busy": False,
        "dialog_finished": False,
        "app_exec_returncode": None,
        "process_exit_code": 1,
    }
    try:
        config = TWStockConfig(
            data_root=Path(args.data_root),
            output_root=Path(args.output_root),
        )
        config.db_file = Path(args.db_file)
        app = QApplication.instance() or QApplication(sys.argv)
        report_service = StockResearchReportReadService(config)
        journal_service = JournalService(config)
        controller = DecisionContinuityController(journal_service)
        journey_service = DecisionOutcomeJourneyService.from_config(
            config,
            journal_path=Path(config.output_root) / "portfolio" / "journal_entries.jsonl",
        )
        context = ResearchStockContextDTO(
            stock_code=args.stock_code,
            result_id=args.result_id,
            decision_date="2026-09-10",
            identity_status="linked",
            source_workspace="workbench",
        )
        worker_started = Event()
        release_worker = Event()

        class BarrierReportReadService:
            def read_report(self, stock_code, *, context=None, cancel_callback=None):
                del cancel_callback
                worker_started.set()
                if not release_worker.wait(timeout=8):
                    raise TimeoutError("busy-close probe worker release timed out")
                return report_service.read_report(stock_code, context=context)

        dialog = StockResearchReportDialog(
            BarrierReportReadService(),
            context,
            journey_service=journey_service,
            continuity_controller=controller,
        )

        def mark_finished(_result: int) -> None:
            receipt["dialog_finished"] = True
            app.quit()

        close_deadline = time.monotonic() + 8

        def request_busy_close() -> None:
            if not worker_started.is_set():
                if time.monotonic() >= close_deadline:
                    receipt["error"] = "report worker did not reach busy barrier"
                    release_worker.set()
                    app.quit()
                    return
                QTimer.singleShot(10, request_busy_close)
                return
            receipt["close_requested_while_busy"] = dialog.is_busy()
            dialog.close()
            # Release only after the UI has requested cooperative cancellation
            # through the existing dialog close path.
            release_worker.set()

        dialog.finished.connect(mark_finished)
        dialog.show()
        QTimer.singleShot(0, request_busy_close)
        # A watchdog only bounds a failed probe; success still exits through
        # the dialog's existing finished signal and cooperative close path.
        QTimer.singleShot(10_000, app.quit)
        exit_code = int(app.exec())
        receipt["app_exec_returncode"] = exit_code
        receipt["process_exit_code"] = int(
            0
            if receipt["dialog_finished"] is True
            and receipt["close_requested_while_busy"] is True
            and exit_code == 0
            else 1
        )
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return int(receipt["process_exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
