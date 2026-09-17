"""Run the real MainWindow recommendation-save delivery/readback probe.

The probe deliberately uses the production ``MainWindow()`` constructor and
the RecommendationView, JournalService, and RecommendationRepository that
the window composes.  Only the recommendation producer input is a bounded
fixture; no page or window composition is replaced.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
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

from app_module.dtos import RecommendationDTO
from app_module.journal_service import JournalService
from app_module.personalization_contract import (
    PersonalizationDeliveryScope,
    canonical_payload_hash,
)
from app_module.personalization_projection import PersonalizationProjectionService
from app_module.personalization_save_adapter import (
    PersonalizationRecommendationSaveAdapter,
)
from ui_qt.main import (
    MainWindow,
    _configure_console_streams,
    _drain_qt_deferred_deletes,
)
from ui_qt.workers.task_worker import running_task_workers

_configure_console_streams()


RESULT_ID = "rec_personalization_mainwindow_probe_20260916"
STOCK_CODE = "2330"
SCOPE_ID = "local_research_scope_v1"
DELIVERY_ID = "delivery_personalization_mainwindow_probe_20260916"
REQUEST_ID = "personalization-mainwindow-probe-20260916"
PREDICTION_ID = "00000000-0000-0000-0000-000000000011"
DATASET_HASH = "sha256:" + ("d" * 64)
COST_SCENARIO_HASH = "sha256:" + ("b" * 64)
UNIVERSE_POLICY_HASH = "sha256:" + ("e" * 64)
LABEL_CONTRACT_ID = "label_projection_v1"
RETURN_BASIS = "close_to_close_event_date"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--receipt", required=True)
    return parser.parse_args()


def _receipt() -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "recommendation-calibration-projection-receipt.v1",
        "result_id": RESULT_ID,
        "decision_date": "2025-02-10",
        "candidate_identity": {"candidate_id": "model_001"},
        "model_id": "model_001",
        "dataset_id": "dataset_001",
        "dataset_hash": DATASET_HASH,
        "label_contract_id": LABEL_CONTRACT_ID,
        "return_basis": RETURN_BASIS,
        "universe_policy_hash": UNIVERSE_POLICY_HASH,
        "source_id": "recommendation_service",
        "selection_contract": {
            "authority": "rule_top_n",
            "score_kind": "rule_total_score",
            "percentile_kind": "rule_percentile",
            "model_ranking_kind": "model_return_bp",
            "top_n_changed_by_model": False,
        },
        "projections": [
            {
                "stock_code": STOCK_CODE,
                "model_version": "model_001",
                "dataset_version": "dataset_001",
                "dataset_hash": DATASET_HASH,
                "cost_scenario_hash": COST_SCENARIO_HASH,
                "horizon": "20 trading days",
                "prediction_id": PREDICTION_ID,
                "label_contract_id": LABEL_CONTRACT_ID,
                "return_basis": RETURN_BASIS,
                "universe_policy_hash": UNIVERSE_POLICY_HASH,
                "calibrated_probability_bp": 5200,
                "status": "active_candidate",
            }
        ],
        "formal_order_allowed": False,
        "production_action_allowed": False,
        "shadow_only": True,
    }
    return {**body, "receipt_hash": canonical_payload_hash(body)}


def _scope() -> PersonalizationDeliveryScope:
    return PersonalizationDeliveryScope.create(
        scope_id=SCOPE_ID,
        scope_type="local",
        delivery_id=DELIVERY_ID,
        declared_at="2025-02-10T08:50:00+00:00",
        decision_at="2025-02-10T09:00:00+00:00",
        available_at="2025-02-10T08:55:00+00:00",
        captured_at="2025-02-10T08:55:00+00:00",
        receipt_created_at="2025-02-10T09:01:00+00:00",
        source="recommendation_service",
    )


def _recommendation() -> RecommendationDTO:
    return RecommendationDTO(
        stock_code=STOCK_CODE,
        stock_name="台積電",
        close_price=Decimal("100.00"),
        price_change=1,
        total_score=80,
        indicator_score=80,
        pattern_score=80,
        volume_score=80,
        recommendation_reasons="real MainWindow save probe",
        industry="半導體",
        regime_match=True,
    )


def _producer_context() -> dict[str, Any]:
    receipt = _receipt()
    scope = _scope()
    return {
        "schema_version": "recommendation-context.v1",
        "result_id": RESULT_ID,
        "as_of_date": "2025-02-10",
        "data_date": "2025-02-10",
        "temporal_contract": "recommendation-producer-clock.v1",
        "temporal_mode": "natural_producer_clock",
        "cutoff_selection": "producer_selected_latest_available_cutoff",
        "cutoff_policy": "source_latest_available_exact",
        "decision_clock_timezone": "UTC",
        "market_calendar_timezone": "Asia/Taipei",
        "prediction_decision_anchor": "actual_producer_decision_at",
        "horizon_anchor": "immutable_projection_receipt",
        "run_started_at": "2025-02-10T08:49:00+00:00",
        "personalization_scope_declared_at": scope.declared_at,
        "available_at": scope.available_at,
        "captured_at": scope.captured_at,
        "decision_at": scope.decision_at,
        "calibration_projection_receipt_created_at": scope.receipt_created_at,
        "calibration_projection_receipt": receipt,
        "calibration_projection_rows": {
            STOCK_CODE: dict(receipt["projections"][0]),
        },
        "personalization_scope": scope.to_dict(),
        "personalization_delivery_scope": scope.to_dict(),
        "personalization_request_id": REQUEST_ID,
    }


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
        "schema_version": "personalization-mainwindow-save-readback-probe.v1",
        "process_id": os.getpid(),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_root": str(data_root),
        "output_root": str(output_root),
        "main_window_constructed": False,
        "real_recommendation_view": False,
        "window_journal_owned": False,
        "view_journal_is_window_journal": False,
        "real_repository": False,
        "fixture_producer_context_bound": False,
        "normal_save_entry_clicked": False,
        "result_readback": False,
        "journal_ack_readback": False,
        "projection_readback": False,
        "result_json_unchanged_after_projection": False,
        "projection_status": "",
        "delivery_status": "",
        "action_state": "",
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
        repository = view.recommendation_repository
        journal = window.journal_service
        receipt["main_window_constructed"] = True
        receipt["real_recommendation_view"] = type(view).__name__ == "RecommendationView"
        receipt["window_journal_owned"] = isinstance(journal, JournalService)
        receipt["view_journal_is_window_journal"] = view.journal_service is journal
        receipt["real_repository"] = repository is not None and type(repository).__name__ == "RecommendationRepository"
        if not (
            receipt["real_recommendation_view"]
            and receipt["window_journal_owned"]
            and receipt["view_journal_is_window_journal"]
            and receipt["real_repository"]
        ):
            raise RuntimeError("MainWindow composition did not retain real recommendation dependencies")

        producer_context = _producer_context()
        producer = view.recommendation_service
        producer.last_run_context = deepcopy(producer_context)
        view.current_recommendations = [_recommendation()]
        view.current_config = {"strategy_config": {"mode": "mainwindow_process_probe"}}
        view.current_profile = None
        view.current_regime = None
        view.save_result_btn.setVisible(True)
        receipt["fixture_producer_context_bound"] = (
            producer.last_run_context == producer_context
        )

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
        if result_id != RESULT_ID or repository is None:
            raise RuntimeError("saved result identity did not preserve the fixture receipt identity")
        loaded = repository.load_result(result_id)
        if loaded is None:
            raise RuntimeError("real MainWindow save did not produce exact result readback")
        adapter = PersonalizationRecommendationSaveAdapter()
        captures = adapter.captures_from_result(loaded)
        if len(captures) != 1 or captures[0].scope.scope_id != SCOPE_ID:
            raise RuntimeError("real MainWindow result readback lacks the local capture")
        result_file = repository.runs_dir / f"{result_id}.json"
        before_projection_bytes = result_file.read_bytes()
        receipt["result_readback"] = True
        receipt["result_id"] = result_id
        receipt["result_path"] = str(result_file)
        receipt["capture_hash"] = captures[0].capture_hash
        receipt["scope_envelope_hash"] = captures[0].scope.envelope_hash

        ack_rows = journal.list_personalization_delivery_acks(
            result_id,
            STOCK_CODE,
            DELIVERY_ID,
        )
        if len(ack_rows) != 1:
            raise RuntimeError("real MainWindow save did not append one delivery ACK")
        receipt["journal_ack_readback"] = True
        receipt["journal_ack_count"] = len(ack_rows)

        projection = PersonalizationProjectionService(
            delivery_reader=journal.list_personalization_delivery_acks,
        ).build_for_candidate(
            result_id=result_id,
            stock_code=STOCK_CODE,
            personalization_scope_id=SCOPE_ID,
            result=loaded,
            projection_receipt=_receipt(),
        )
        if (
            projection.status != "linked_prediction"
            or projection.delivery_status != "delivered"
            or projection.evidence is None
            or projection.evidence.action_state != "not_recorded"
        ):
            raise RuntimeError("real MainWindow ACK readback did not produce delivered read projection")
        receipt["projection_readback"] = True
        receipt["projection_status"] = projection.status
        receipt["delivery_status"] = projection.delivery_status
        receipt["action_state"] = projection.evidence.action_state
        receipt["late_delivery"] = projection.late_delivery
        receipt["result_json_unchanged_after_projection"] = (
            result_file.read_bytes() == before_projection_bytes
        )
        if not receipt["result_json_unchanged_after_projection"]:
            raise RuntimeError("read projection mutated the immutable recommendation result")

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
            and receipt["real_repository"]
            and receipt["fixture_producer_context_bound"]
            and receipt["normal_save_entry_clicked"]
            and receipt["result_readback"]
            and receipt["journal_ack_readback"]
            and receipt["projection_readback"]
            and receipt["result_json_unchanged_after_projection"]
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
