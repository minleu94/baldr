"""Run the real MainWindow recommendation-save delivery/readback probe.

The probe deliberately uses the production ``MainWindow()`` constructor and
the RecommendationView, JournalService, and canonical RecommendationComposition
that the window composes. Only the recommendation execution input is a bounded
fixture; no page or window composition is replaced.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app_module.journal_service import JournalService
from app_module.recommendation.composition import RecommendationComposition
from app_module.recommendation.contracts import (
    Context,
    ExecutionStatus,
    RecommendationExecution,
    Request,
)
from decision_module.recommendation.contracts import DecisionBatch, RecommendationItem
from ui_qt.main import (
    MainWindow,
    _configure_console_streams,
    _drain_qt_deferred_deletes,
)
from ui_qt.workers.task_worker import running_task_workers

_configure_console_streams()


RESULT_ID = "rec_qt_manual_save_probe_20260923"
STOCK_CODE = "2330"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--receipt", required=True)
    return parser.parse_args()


def _execution() -> RecommendationExecution:
    from ui_qt.views.recommendation.execution_coordinator import (
        RecommendationExecutionRequest,
    )

    request_capture = RecommendationExecutionRequest(
        {
            "patterns": {"selected": ["W底"]},
            "signals": {"technical_indicators": ["trend"]},
            "filters": {"probe": "qt-manual-save"},
        }
    )
    decision_date = date(2026, 9, 23)
    decision_at = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)
    item = RecommendationItem(
        stock_code=STOCK_CODE,
        stock_name="台積電",
        close_price=900,
        price_change=15,
        rule_score=85,
        indicator_score=80,
        pattern_score=90,
        volume_score=85,
        reason_text="bounded Qt manual-save readback probe",
        industry="半導體",
        regime_match=True,
        rank=1,
    )
    return RecommendationExecution(
        result_id=RESULT_ID,
        request=Request(
            as_of_date=decision_date,
            config_snapshot=request_capture.config_snapshot,
            max_stocks=200,
            top_n=50,
        ),
        context=Context(
            as_of_date=decision_date,
            decision_at=decision_at,
            available_at=decision_at,
            created_at=decision_at,
        ),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=(item,), regime="Trend"),
    )


def _not_visible(widget: object) -> bool:
    try:
        return not bool(widget.isVisible())  # type: ignore[attr-defined]
    except RuntimeError:
        return True


def main() -> int:
    args = _parse_args()
    data_root = Path(args.data_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    receipt_path = Path(args.receipt).expanduser().resolve()
    os.environ["DATA_ROOT"] = str(data_root)
    os.environ["OUTPUT_ROOT"] = str(output_root)
    os.environ["PROFILE"] = "prod"

    # Do not let an installed formal runtime binding escape this isolated
    # process.  The probe is only for the research save/readback boundary.
    for name in (
        "FORMAL_DAILY_RUNTIME_CONFIG",
        "FORMAL_DAILY_RUNTIME_CONFIG_ROOT",
        "FORMAL_DAILY_ROLLING_CALENDAR_BUNDLE",
        "FORMAL_DAILY_PORTFOLIO_CLOCK_MANIFEST",
    ):
        os.environ.pop(name, None)
    os.environ["FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE"] = str(
        output_root / ".missing-formal-runtime-binding.json"
    )

    receipt: dict[str, Any] = {
        "schema_version": "qt-manual-save-no-personal-ack-probe.v1",
        "process_id": os.getpid(),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_root": str(data_root),
        "output_root": str(output_root),
        "main_window_constructed": False,
        "real_recommendation_view": False,
        "window_journal_owned": False,
        "view_journal_is_window_journal": False,
        "real_canonical_composition": False,
        "fixture_execution_bound": False,
        "normal_save_entry_clicked": False,
        "result_readback": False,
        "personal_scope_present": False,
        "no_personal_ack_readback": False,
        "exact_query_readback": False,
        "result_artifact_unchanged_after_query": False,
        "close_requests": 0,
        "watchdog_fired": False,
        "app_exec_returncode": None,
        "window_hidden_after_exec": False,
        "remaining_workers_after_exec": None,
        "process_exit_code": 1,
    }
    window: MainWindow | None = None
    application: QApplication | None = None
    patched_dialog_methods: tuple[Any, Any, Any] | None = None

    try:
        application = QApplication.instance() or QApplication(sys.argv)
        window = MainWindow()
        view = window.recommendation_view
        composition = view._get_recommendation_composition()
        journal = window.journal_service
        receipt["main_window_constructed"] = True
        receipt["real_recommendation_view"] = type(view).__name__ == "RecommendationView"
        receipt["window_journal_owned"] = isinstance(journal, JournalService)
        receipt["view_journal_is_window_journal"] = view.journal_service is journal
        receipt["real_canonical_composition"] = isinstance(
            composition,
            RecommendationComposition,
        )
        if not (
            receipt["real_recommendation_view"]
            and receipt["window_journal_owned"]
            and receipt["view_journal_is_window_journal"]
            and receipt["real_canonical_composition"]
        ):
            raise RuntimeError("MainWindow composition did not retain real recommendation dependencies")

        execution = _execution()
        view.current_execution = execution
        view.current_config = view._execution_config(execution)
        view.current_profile = None
        view.current_regime = None
        view.save_result_btn.setVisible(True)
        receipt["fixture_execution_bound"] = view.current_execution is execution

        from ui_qt.views import recommendation_view as view_module

        messages: list[str] = []
        patched_dialog_methods = (
            view_module.QInputDialog.getText,
            view_module.QMessageBox.information,
            view_module.QMessageBox.critical,
        )
        view_module.QInputDialog.getText = lambda *args, **kwargs: (
            "MainWindow process save probe",
            True,
        )
        view_module.QMessageBox.information = (
            lambda *args, **kwargs: messages.append(str(args[-1]))
        )
        view_module.QMessageBox.critical = (
            lambda *args, **kwargs: messages.append(str(args[-1]))
        )
        view.show()
        application.processEvents()
        view.save_result_btn.click()
        application.processEvents()
        receipt["normal_save_entry_clicked"] = True
        if not messages or "推薦結果已保存" not in messages[-1]:
            raise RuntimeError("normal recommendation save entry did not report success")

        result_id = str(view.current_result_id or "")
        if result_id != RESULT_ID:
            raise RuntimeError("saved result identity did not preserve the fixture receipt identity")
        loaded = composition.queries.get(result_id)
        if loaded is None or loaded.execution != execution:
            raise RuntimeError("real MainWindow save did not produce exact query readback")
        before_query_bytes = composition.store.read_artifact(result_id)
        if before_query_bytes is None:
            raise RuntimeError("canonical result artifact was not published")
        receipt["result_readback"] = True
        receipt["result_id"] = result_id
        receipt["result_path"] = loaded.artifact_location
        receipt["payload_hash"] = loaded.payload_hash
        receipt["personal_scope_present"] = bool(
            getattr(execution, "personalization_scope", None)
            or getattr(execution, "personalization_scope_id", None)
        )

        ack_rows = journal.list_personalization_delivery_acks(
            result_id,
            STOCK_CODE,
            "",
        )
        if ack_rows:
            raise RuntimeError("Qt manual save unexpectedly appended personal delivery ACK")
        if receipt["personal_scope_present"]:
            raise RuntimeError("Qt manual-save probe unexpectedly includes personal scope")
        receipt["no_personal_ack_readback"] = True
        receipt["personal_ack_count"] = len(ack_rows)
        receipt["exact_query_readback"] = composition.queries.get(result_id) == loaded
        receipt["result_artifact_unchanged_after_query"] = (
            composition.store.read_artifact(result_id) == before_query_bytes
        )
        if not receipt["result_artifact_unchanged_after_query"]:
            raise RuntimeError("exact read projection mutated the immutable recommendation artifact")

        # Restore modal methods before entering the normal close lifecycle.
        view_module.QInputDialog.getText = patched_dialog_methods[0]
        view_module.QMessageBox.information = patched_dialog_methods[1]
        view_module.QMessageBox.critical = patched_dialog_methods[2]
        patched_dialog_methods = None

        window.show()
        application.processEvents()
        receipt["close_requests"] = 1
        window.close()

        def finish_when_idle() -> None:
            if window is None or application is None:
                return
            if _not_visible(window) and not running_task_workers():
                application.quit()
                return
            QTimer.singleShot(20, finish_when_idle)

        def watchdog() -> None:
            receipt["watchdog_fired"] = True
            if application is not None:
                application.quit()

        QTimer.singleShot(0, finish_when_idle)
        QTimer.singleShot(20_000, watchdog)
        receipt["app_exec_returncode"] = int(application.exec())
        receipt["window_hidden_after_exec"] = _not_visible(window)
        receipt["remaining_workers_after_exec"] = len(running_task_workers())
        receipt["process_exit_code"] = int(
            0
            if receipt["main_window_constructed"]
            and receipt["real_recommendation_view"]
            and receipt["window_journal_owned"]
            and receipt["view_journal_is_window_journal"]
            and receipt["real_canonical_composition"]
            and receipt["fixture_execution_bound"]
            and receipt["normal_save_entry_clicked"]
            and receipt["result_readback"]
            and receipt["personal_scope_present"] is False
            and receipt["no_personal_ack_readback"]
            and receipt["exact_query_readback"]
            and receipt["result_artifact_unchanged_after_query"]
            and receipt["close_requests"] == 1
            and receipt["watchdog_fired"] is False
            and receipt["window_hidden_after_exec"]
            and receipt["remaining_workers_after_exec"] == 0
            and receipt["app_exec_returncode"] == 0
            else 1
        )
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if patched_dialog_methods is not None:
            try:
                from ui_qt.views import recommendation_view as view_module

                view_module.QInputDialog.getText = patched_dialog_methods[0]
                view_module.QMessageBox.information = patched_dialog_methods[1]
                view_module.QMessageBox.critical = patched_dialog_methods[2]
            except Exception:
                pass
        if window is not None:
            try:
                if not _not_visible(window):
                    window.close()
            except RuntimeError:
                pass
            if application is not None:
                try:
                    _drain_qt_deferred_deletes(application, (window,))
                except (RuntimeError, TypeError):
                    pass
        receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return int(receipt["process_exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
