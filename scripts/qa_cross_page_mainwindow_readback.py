"""Independent MainWindow readback/render probe for a saved decision journey."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
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

from app_module.continuity_review_projection import ContinuityReviewProjectionService
from app_module.research_session import ResearchStockContextDTO
from ui_qt.main import (
    MainWindow,
    _configure_console_streams,
    _drain_qt_deferred_deletes,
)
from ui_qt.workers.task_worker import running_task_workers

_configure_console_streams()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--result-id", required=True)
    parser.add_argument("--receipt", required=True)
    return parser.parse_args()


def _text(mapping: object, key: str) -> str:
    if not isinstance(mapping, dict):
        return ""
    return str(mapping.get(key) or "").strip()


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _saved_recommendation_stock_code(row: object) -> str | None:
    """解析保存推薦列的雙語代號；同列矛盾時不猜測。"""

    if not isinstance(row, dict):
        return None
    english_code = _text(row, "stock_code")
    chinese_code = _text(row, "證券代號")
    if english_code and chinese_code and english_code != chinese_code:
        return None
    return english_code or chinese_code or None


def _exact_saved_recommendation(
    recommendations: object,
    stock_code: str,
) -> dict[str, Any] | None:
    """只接受單一精確保存列，並拒絕要求股票的 alias 矛盾。"""

    if not isinstance(recommendations, list) or not stock_code:
        return None
    matches: list[dict[str, Any]] = []
    for row in recommendations:
        if not isinstance(row, dict):
            continue
        english_code = _text(row, "stock_code")
        chinese_code = _text(row, "證券代號")
        if (
            english_code
            and chinese_code
            and english_code != chinese_code
            and stock_code in {english_code, chinese_code}
        ):
            return None
        if _saved_recommendation_stock_code(row) == stock_code:
            matches.append(row)
    return matches[0] if len(matches) == 1 else None


def _not_visible(widget: object) -> bool:
    try:
        return not bool(widget.isVisible())  # type: ignore[attr-defined]
    except RuntimeError:
        return True


class _ProbeMainWindow(MainWindow):
    """保留正式 MainWindow 關閉流程，並記錄 idle close 次數。"""

    def __init__(self) -> None:
        self.close_event_count = 0
        super().__init__()

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
        "main_window_recreated": False,
        "persisted_readback": False,
        "persisted_identity_consistent": False,
        "report_loaded": False,
        "journey_loaded": False,
        "dialog_finished": False,
        "exact_identity_visible": False,
        "idle_close_requests": 0,
        "main_window_close_event_count": 0,
        "watchdog_fired": False,
        "forced_termination": False,
        "app_exec_returncode": None,
        "process_exit_code": 1,
    }
    window: _ProbeMainWindow | None = None

    try:
        result_path = output_root / "recommendation" / "runs" / f"{args.result_id}.json"
        watchlist_path = output_root / "watchlist" / "default.json"
        trades_path = output_root / "portfolio" / "trades.jsonl"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        watchlist = json.loads(watchlist_path.read_text(encoding="utf-8"))
        trades = [
            json.loads(line)
            for line in trades_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        watch_item = next(
            item
            for item in watchlist["items"]
            if _text(item.get("decision_identity"), "result_id") == args.result_id
        )
        watch_identity = _mapping(watch_item.get("decision_identity"))
        watch_stock_code = _text(watch_identity, "stock_code") or _text(
            watch_item,
            "stock_code",
        )
        trade = next(item for item in trades if _text(item, "source_id") == args.result_id)
        projection = ContinuityReviewProjectionService.from_output_root(output_root).project(
            as_of="2099-01-01T00:00:00+00:00"
        )
        continuity_item = next(
            item
            for item in projection.items
            if item.candidate_key == (args.result_id, "2330")
        )

        config = _mapping(result.get("config"))
        run_context = _mapping(result.get("run_context"))
        recommendations = result.get("recommendations")
        recommendation = _exact_saved_recommendation(
            recommendations,
            watch_stock_code,
        )
        if recommendation is None:
            raise ValueError(
                "saved recommendation lacks one exact, non-conflicting row "
                f"for stock_code={watch_stock_code!r}"
            )
        result_id = _text(result, "result_id")
        result_stock_code = _saved_recommendation_stock_code(recommendation) or ""
        result_decision_date = _text(config, "as_of_date") or _text(
            run_context, "as_of_date"
        )
        result_data_date = _text(config, "data_date") or _text(
            run_context, "data_date"
        )
        result_snapshot_id = _text(config, "source_snapshot_id") or _text(
            run_context, "source_snapshot_id"
        )
        result_snapshot_hash = _text(config, "source_snapshot_hash") or _text(
            run_context, "source_snapshot_hash"
        )
        trade_summary = _mapping(trade.get("source_summary"))
        expected_identity = {
            "result_id": args.result_id,
            "stock_code": result_stock_code,
            "decision_date": result_decision_date,
            "data_date": result_data_date,
            "source_snapshot_id": result_snapshot_id,
            "source_snapshot_hash": result_snapshot_hash,
        }
        context = ResearchStockContextDTO(
            stock_code=_text(watch_identity, "stock_code") or result_stock_code,
            stock_name=_text(watch_item, "stock_name") or _text(recommendation, "證券名稱"),
            decision_date=(
                _text(watch_identity, "decision_date")
                or result_decision_date
            ),
            data_date=result_data_date,
            result_id=_text(watch_identity, "result_id") or result_id or args.result_id,
            identity_status=_text(watch_identity, "identity_status") or "linked",
            source_snapshot_id=(
                _text(watch_identity, "source_snapshot_id")
                or result_snapshot_id
            ),
            source_snapshot_hash=(
                _text(watch_identity, "source_snapshot_hash")
                or result_snapshot_hash
            ),
            source_id=_text(watch_item, "source_id") or _text(config, "source_id"),
            source_kind=_text(config, "source_kind") or "persisted_recommendation",
            source_workspace="watchlist",
        )
        watch_readback = {
            "result_id": _text(watch_identity, "result_id"),
            "stock_code": _text(watch_identity, "stock_code")
            or _text(watch_item, "stock_code"),
            "decision_date": _text(watch_identity, "decision_date"),
            "source_snapshot_id": _text(watch_identity, "source_snapshot_id"),
            "source_snapshot_hash": _text(watch_identity, "source_snapshot_hash"),
        }
        trade_readback = {
            "result_id": _text(trade, "source_id")
            or _text(trade_summary, "result_id"),
            "stock_code": _text(trade, "stock_code")
            or _text(trade_summary, "stock_code"),
            "decision_date": _text(trade_summary, "decision_date")
            or _text(trade, "trade_date"),
            "source_snapshot_id": _text(trade_summary, "source_snapshot_id"),
            "source_snapshot_hash": _text(trade, "source_snapshot_hash")
            or _text(trade_summary, "source_snapshot_hash"),
        }
        continuity_readback = {
            "result_id": continuity_item.result_id,
            "stock_code": continuity_item.stock_code,
            "decision_date": continuity_item.decision_date,
            "source_snapshot_id": continuity_item.source_snapshot_id,
            "source_snapshot_hash": continuity_item.source_snapshot_hash,
            "next_review_at": continuity_item.next_review_at,
        }
        persisted_identity_consistent = (
            result_id == expected_identity["result_id"]
            and result_stock_code == expected_identity["stock_code"]
            and result_decision_date == expected_identity["decision_date"]
            and result_snapshot_id == expected_identity["source_snapshot_id"]
            and result_snapshot_hash == expected_identity["source_snapshot_hash"]
            and watch_readback == {
                "result_id": expected_identity["result_id"],
                "stock_code": expected_identity["stock_code"],
                "decision_date": expected_identity["decision_date"],
                "source_snapshot_id": expected_identity["source_snapshot_id"],
                "source_snapshot_hash": expected_identity["source_snapshot_hash"],
            }
            and trade_readback == {
                "result_id": expected_identity["result_id"],
                "stock_code": expected_identity["stock_code"],
                "decision_date": expected_identity["decision_date"],
                "source_snapshot_id": expected_identity["source_snapshot_id"],
                "source_snapshot_hash": expected_identity["source_snapshot_hash"],
            }
            and continuity_readback["result_id"] == expected_identity["result_id"]
            and continuity_readback["stock_code"] == expected_identity["stock_code"]
            and continuity_readback["decision_date"] == expected_identity["decision_date"]
            and continuity_readback["source_snapshot_id"]
            == expected_identity["source_snapshot_id"]
            and continuity_readback["source_snapshot_hash"]
            == expected_identity["source_snapshot_hash"]
            and continuity_item.candidate_key_text
            == f"{expected_identity['result_id']}:{expected_identity['stock_code']}"
        )
        receipt["persisted_readback"] = bool(persisted_identity_consistent)
        receipt["persisted_identity_consistent"] = bool(persisted_identity_consistent)
        receipt["persisted_identity"] = {
            "result": {
                **expected_identity,
            },
            "watchlist": watch_readback,
            "portfolio_trade": trade_readback,
            "continuity": continuity_readback,
            "candidate_key": continuity_item.candidate_key_text,
        }

        app = QApplication.instance() or QApplication(sys.argv)
        window = _ProbeMainWindow()
        receipt["main_window_recreated"] = isinstance(window, MainWindow)
        window.show()
        window._open_stock_research_context(context)
        dialog = window._stock_research_report_dialog
        if dialog is None:
            raise RuntimeError("MainWindow did not create StockResearchReportDialog")

        report_loaded = False
        journey_loaded = False
        close_started = False

        def finish_after_close() -> None:
            if _not_visible(window) and not running_task_workers():
                app.quit()
            else:
                QTimer.singleShot(20, finish_after_close)

        def mark_dialog_finished(_result: int) -> None:
            receipt["dialog_finished"] = True

        dialog.finished.connect(mark_dialog_finished)

        def finish_when_both_views_loaded() -> None:
            nonlocal close_started
            if close_started or not report_loaded or not journey_loaded:
                return
            close_started = True
            receipt["idle_close_requests"] = int(
                receipt["idle_close_requests"]
            ) + 1
            dialog.close()
            window.close()
            QTimer.singleShot(0, finish_after_close)

        def on_report_loaded(report: object) -> None:
            nonlocal report_loaded
            report_context = dialog.report_view.context
            journey_context = (
                dialog.journey_view.context
                if dialog.journey_view is not None
                else None
            )
            session_text = window.session_context_strip._full_context_text
            rendered_identity = {
                "report_stock_code": str(getattr(report, "stock_code", "")),
                "report_context": {
                    "result_id": getattr(report_context, "result_id", ""),
                    "stock_code": getattr(report_context, "stock_code", ""),
                    "decision_date": getattr(report_context, "decision_date", ""),
                    "data_date": getattr(report_context, "data_date", ""),
                    "source_snapshot_id": getattr(
                        report_context, "source_snapshot_id", ""
                    ),
                    "source_snapshot_hash": getattr(
                        report_context, "source_snapshot_hash", ""
                    ),
                },
                "journey_context": {
                    "result_id": getattr(journey_context, "result_id", "")
                    if journey_context is not None
                    else "",
                    "stock_code": getattr(journey_context, "stock_code", "")
                    if journey_context is not None
                    else "",
                    "decision_date": getattr(journey_context, "decision_date", "")
                    if journey_context is not None
                    else "",
                    "data_date": getattr(journey_context, "data_date", "")
                    if journey_context is not None
                    else "",
                    "source_snapshot_id": getattr(
                        journey_context, "source_snapshot_id", ""
                    )
                    if journey_context is not None
                    else "",
                    "source_snapshot_hash": getattr(
                        journey_context, "source_snapshot_hash", ""
                    )
                    if journey_context is not None
                    else "",
                },
                "session_context_text": session_text,
            }
            receipt["report_loaded"] = True
            existing_rendered = receipt.setdefault("rendered_identity", {})
            if not isinstance(existing_rendered, dict):
                existing_rendered = {}
                receipt["rendered_identity"] = existing_rendered
            existing_rendered.update(rendered_identity)
            report_loaded = True
            finish_when_both_views_loaded()

        def on_journey_loaded(journey: object) -> None:
            nonlocal journey_loaded
            journey_view = dialog.journey_view
            if journey_view is None:
                receipt["error"] = "journey_loaded_without_journey_view"
                return
            result_record = getattr(journey, "recommendation_result", None)
            source_identity = getattr(result_record, "source_identity", None)
            candidates = getattr(result_record, "candidates", ())
            candidate_key = (context.result_id, context.stock_code)
            candidate = next(
                (
                    item
                    for item in candidates
                    if getattr(item, "candidate_key", None) == candidate_key
                ),
                None,
            )
            maturity = tuple(
                item
                for item in getattr(journey, "outcome_maturity", ())
                if getattr(item, "candidate_key", None) == candidate_key
            )
            controls = journey_view.continuity_controls
            controls_identity = getattr(controls, "identity", None)
            controls_state = getattr(controls, "state", None)
            rendered = receipt.setdefault("rendered_identity", {})
            if not isinstance(rendered, dict):
                rendered = {}
                receipt["rendered_identity"] = rendered
            rendered["journey"] = {
                "result_id": getattr(result_record, "result_id", ""),
                "candidate_key": list(getattr(candidate, "candidate_key", ()) or ()),
                "candidate_found": candidate is not None,
                "decision_date": getattr(result_record, "decision_date", ""),
                "source_snapshot_id": getattr(source_identity, "source_snapshot_id", ""),
                "source_snapshot_hash": getattr(
                    source_identity, "source_snapshot_hash", ""
                ),
                "maturity_rows": [
                    {
                        "window_days": getattr(item, "window_days", None),
                        "link_status": str(getattr(item, "status", "")),
                        "outcome_status": getattr(item, "outcome_status", ""),
                    }
                    for item in maturity
                ],
                "status_text": journey_view.status_label.text(),
            }
            rendered["journey_controls"] = {
                "candidate_key": list(getattr(controls_identity, "candidate_key", ()) or ())
                if controls_identity is not None
                else [],
                "identity_status": getattr(controls_identity, "identity_status", "")
                if controls_identity is not None
                else "",
                "next_review_at": getattr(controls_state, "next_review_at", "")
                if controls_state is not None
                else "",
                "status_text": controls.status_label.text() if controls is not None else "",
                "accept_enabled": bool(controls.accept_button.isEnabled())
                if controls is not None
                else False,
            }
            journey_loaded = (
                result_record is not None
                and getattr(result_record, "result_id", "") == context.result_id
                and candidate is not None
                and getattr(candidate, "candidate_key", None) == candidate_key
                and source_identity is not None
                and getattr(source_identity, "decision_date", "")
                == expected_identity["decision_date"]
                and getattr(source_identity, "source_snapshot_id", "")
                == expected_identity["source_snapshot_id"]
                and getattr(source_identity, "source_snapshot_hash", "")
                == expected_identity["source_snapshot_hash"]
                and controls is not None
                and controls_identity is not None
                and controls_identity.candidate_key == candidate_key
                and controls_identity.identity_status == "linked"
                and controls_state is not None
                and controls_state.next_review_at == continuity_item.next_review_at
                and continuity_item.next_review_at in controls.status_label.text()
            )
            receipt["journey_loaded"] = bool(journey_loaded)
            finish_when_both_views_loaded()

        def on_report_failed(error: str) -> None:
            receipt["error"] = f"report_failed: {error}"
            window.close()
            QTimer.singleShot(0, finish_after_close)

        def on_journey_failed(error: str) -> None:
            receipt["error"] = f"journey_failed: {error}"
            window.close()
            QTimer.singleShot(0, finish_after_close)

        dialog.report_view.reportLoaded.connect(on_report_loaded)
        dialog.report_view.reportFailed.connect(on_report_failed)
        if dialog.journey_view is None:
            raise RuntimeError("MainWindow dialog did not recreate the Journey view")
        dialog.journey_view.journeyLoaded.connect(on_journey_loaded)
        dialog.journey_view.journeyFailed.connect(on_journey_failed)

        def watchdog() -> None:
            receipt["watchdog_fired"] = True
            app.quit()

        QTimer.singleShot(20_000, watchdog)
        app_exec_returncode = int(app.exec())
        receipt["app_exec_returncode"] = app_exec_returncode
        receipt["window_hidden_after_exec"] = _not_visible(window)
        receipt["main_window_close_event_count"] = window.close_event_count
        receipt["remaining_workers_after_exec"] = len(running_task_workers())
        rendered_identity = receipt.get("rendered_identity")
        report_identity = (
            rendered_identity.get("report_context", {})
            if isinstance(rendered_identity, dict)
            else {}
        )
        journey_context_identity = (
            rendered_identity.get("journey_context", {})
            if isinstance(rendered_identity, dict)
            else {}
        )
        journey_identity = (
            rendered_identity.get("journey", {})
            if isinstance(rendered_identity, dict)
            else {}
        )
        controls_identity = (
            rendered_identity.get("journey_controls", {})
            if isinstance(rendered_identity, dict)
            else {}
        )
        session_text = (
            rendered_identity.get("session_context_text", "")
            if isinstance(rendered_identity, dict)
            else ""
        )
        receipt["exact_identity_visible"] = bool(
            receipt.get("persisted_identity_consistent") is True
            and report_identity
            == {
                "result_id": expected_identity["result_id"],
                "stock_code": expected_identity["stock_code"],
                "decision_date": expected_identity["decision_date"],
                "data_date": expected_identity["data_date"],
                "source_snapshot_id": expected_identity["source_snapshot_id"],
                "source_snapshot_hash": expected_identity["source_snapshot_hash"],
            }
            and journey_context_identity
            == {
                "result_id": expected_identity["result_id"],
                "stock_code": expected_identity["stock_code"],
                "decision_date": expected_identity["decision_date"],
                "data_date": expected_identity["data_date"],
                "source_snapshot_id": expected_identity["source_snapshot_id"],
                "source_snapshot_hash": expected_identity["source_snapshot_hash"],
            }
            and journey_identity.get("candidate_found") is True
            and journey_identity.get("result_id") == expected_identity["result_id"]
            and journey_identity.get("candidate_key")
            == [expected_identity["result_id"], expected_identity["stock_code"]]
            and journey_identity.get("decision_date")
            == expected_identity["decision_date"]
            and journey_identity.get("source_snapshot_id")
            == expected_identity["source_snapshot_id"]
            and journey_identity.get("source_snapshot_hash")
            == expected_identity["source_snapshot_hash"]
            and controls_identity.get("candidate_key")
            == [expected_identity["result_id"], expected_identity["stock_code"]]
            and controls_identity.get("identity_status") == "linked"
            and controls_identity.get("next_review_at")
            == continuity_item.next_review_at
            and continuity_item.next_review_at in controls_identity.get("status_text", "")
            and all(value in session_text for value in (
                expected_identity["result_id"],
                expected_identity["stock_code"],
                expected_identity["decision_date"],
            ))
        )
        receipt["process_exit_code"] = int(
            0
            if receipt["main_window_recreated"] is True
            and receipt["persisted_readback"] is True
            and receipt["persisted_identity_consistent"] is True
            and receipt["report_loaded"] is True
            and receipt["dialog_finished"] is True
            and receipt["idle_close_requests"] == 1
            and receipt["main_window_close_event_count"] == 1
            and receipt["journey_loaded"] is True
            and receipt["exact_identity_visible"] is True
            and receipt["watchdog_fired"] is False
            and receipt["forced_termination"] is False
            and receipt["window_hidden_after_exec"] is True
            and receipt["remaining_workers_after_exec"] == 0
            and app_exec_returncode == 0
            else 1
        )
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if window is not None:
            app = QApplication.instance()
            if app is not None:
                try:
                    _drain_qt_deferred_deletes(app, (window,))
                except (RuntimeError, TypeError):
                    pass
            receipt["main_window_close_event_count"] = window.close_event_count
        receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return int(receipt["process_exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
