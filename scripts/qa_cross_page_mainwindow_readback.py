"""以全新 MainWindow 查回並呈現已保存決策旅程的獨立探針。"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app_module.continuity_review_projection import ContinuityReviewProjectionService
from app_module.portfolio_source_adapter import stable_snapshot_hash
from app_module.recommendation.contracts import ExecutionStatus, RecommendationExecution
from app_module.research_session import ResearchStockContextDTO
from app_module.saved_recommendation_queries import (
    build_recommendation_execution_queries,
    execution_result_config,
    saved_recommendation_capture_projection,
)
from data_module.config import TWStockConfig
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
    if not isinstance(mapping, Mapping):
        return ""
    return str(mapping.get(key) or "").strip()


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _identity_text(value: object, field_name: str) -> str:
    if value is None:
        return ""
    if type(value) is date:
        return value.isoformat()
    if type(value) is str:
        return value.strip()
    raise ValueError(f"保存的 {field_name} 型別無法作身份核對")


def _consistent_identity_fact(field_name: str, *values: object) -> str:
    normalized = tuple(
        text for text in (_identity_text(value, field_name) for value in values) if text
    )
    if len(set(normalized)) > 1:
        raise ValueError(f"保存的 {field_name} facts 彼此矛盾")
    return normalized[0] if normalized else ""


def _canonical_json_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _request_config(execution: RecommendationExecution) -> Mapping[str, Any]:
    snapshot = execution.request.config_snapshot
    if snapshot is None:
        return {}
    raw_config_json = snapshot.raw_config_json
    if type(raw_config_json) is not str:
        raise ValueError("保存的 Request.config_snapshot 缺少 JSON 文字")
    document = json.loads(raw_config_json)
    if not isinstance(document, Mapping):
        raise ValueError("保存的 Request.config_snapshot 不是 JSON object")
    return document


def _canonical_identity_facts(
    execution: RecommendationExecution,
) -> dict[str, str]:
    result_config = execution_result_config(execution)
    request_config = _request_config(execution)
    request = execution.request
    context = execution.context
    result_id = execution.result_id
    universe_identity = context.universe_identity
    universe_snapshot = (
        universe_identity.snapshot if universe_identity is not None else None
    )
    if universe_snapshot is None:
        raise ValueError("saved execution lacks typed universe snapshot identity")
    raw_snapshot_spec = universe_snapshot.universe_snapshot_spec_json
    if type(raw_snapshot_spec) is not str:
        raise ValueError("saved universe snapshot 缺少 spec JSON 文字")
    snapshot_spec = json.loads(raw_snapshot_spec)
    if not isinstance(snapshot_spec, Mapping):
        raise ValueError("saved universe snapshot spec 必須是 JSON object")
    raw_universe_codes = snapshot_spec.get("selected_codes")
    if type(raw_universe_codes) is not list or any(
        type(code) is not str for code in raw_universe_codes
    ):
        raise ValueError("saved universe snapshot selected_codes 必須是字串清單")
    universe_codes = cast(list[str], raw_universe_codes)
    universe_code_set = set(universe_codes)
    item_codes = tuple(item.stock_code for item in execution.items)
    if (
        universe_codes != sorted(universe_code_set)
        or type(snapshot_spec.get("selected_count")) is not int
        or snapshot_spec.get("selected_count") != len(universe_codes)
        or snapshot_spec.get("selected_codes_hash")
        != _canonical_json_hash({"selected_codes": universe_codes})
        or len(set(item_codes)) != len(item_codes)
        or any(code not in universe_code_set for code in item_codes)
        or snapshot_spec.get("decision_date")
        != _identity_text(context.as_of_date, "context.as_of_date")
        or snapshot_spec.get("source_provider_id")
        != universe_snapshot.universe_snapshot_source_provider_id
        or universe_snapshot.universe_snapshot_selected_codes_hash
        != _canonical_json_hash({"selected_codes": universe_codes})
        or universe_snapshot.universe_snapshot_hash
        != _canonical_json_hash(snapshot_spec)
        or universe_snapshot.universe_snapshot_id
        != "recommendation-universe-snapshot-v1:"
        + _canonical_json_hash(snapshot_spec).removeprefix("sha256:")
    ):
        raise ValueError(
            "saved universe snapshot facts do not match its input universe or execution items"
        )
    provider_id = _consistent_identity_fact(
        "source_provider_id",
        request_config.get("source_id"),
        universe_snapshot.universe_snapshot_source_provider_id,
    )
    if not provider_id:
        raise ValueError("request source provider identity is absent")
    decision_date = _consistent_identity_fact(
        "decision_date",
        result_config.get("decision_date"),
        request_config.get("decision_date"),
    )
    as_of_date = _consistent_identity_fact(
        "as_of_date",
        result_config.get("as_of_date"),
        request_config.get("as_of_date"),
        context.as_of_date,
        request.as_of_date,
    )
    if not decision_date:
        decision_date = as_of_date
    data_date = _consistent_identity_fact(
        "data_date",
        result_config.get("data_date"),
        request_config.get("data_date"),
    )
    if not data_date:
        data_date = _consistent_identity_fact(
            "data_as_of_date",
            result_config.get("data_as_of_date"),
            request_config.get("data_as_of_date"),
        )
    return {
        "result_id": result_id,
        "decision_date": decision_date,
        "data_date": data_date,
        "source_snapshot_id": universe_snapshot.universe_snapshot_id or "",
        "source_snapshot_hash": universe_snapshot.universe_snapshot_hash or "",
        "universe_snapshot_id": universe_snapshot.universe_snapshot_id or "",
        "universe_snapshot_hash": universe_snapshot.universe_snapshot_hash or "",
        "request_source_snapshot_id": _consistent_identity_fact(
            "source_snapshot_id",
            result_config.get("source_snapshot_id"),
            request_config.get("source_snapshot_id"),
        ),
        "request_source_snapshot_hash": _consistent_identity_fact(
            "source_snapshot_hash",
            result_config.get("source_snapshot_hash"),
            request_config.get("source_snapshot_hash"),
        ),
    }


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if type(value) is date:
        return value.isoformat()
    if type(value) is datetime:
        return value.isoformat()
    return value


def _receipt_int(receipt: Mapping[str, object], field_name: str) -> int:
    value = receipt.get(field_name)
    if type(value) is not int:
        raise ValueError(f"QA receipt {field_name} 必須是整數")
    return value


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


def _read_update_process_state(window: object) -> tuple[bool | None, int | None, str | None]:
    update_view = getattr(window, "update_view", None)
    if update_view is None:
        return None, None, "update_view_missing"
    process = getattr(update_view, "_tpex_background_process", None)
    process_id_raw = getattr(process, "pid", None)
    process_id = (
        process_id_raw
        if type(process_id_raw) is int and process_id_raw > 0
        else None
    )
    probe = getattr(update_view, "has_running_background_process", None)
    if not callable(probe):
        return None, process_id, "update_process_probe_unavailable"
    try:
        is_running = probe()
    except Exception as exc:  # noqa: BLE001 - unknown process state must block close
        return None, process_id, f"update_process_probe_error:{type(exc).__name__}"
    if type(is_running) is not bool:
        return (
            None,
            process_id,
            f"update_process_probe_invalid_type:{type(is_running).__name__}",
        )
    return is_running, process_id, None


def _read_close_state(window: object, dialog: object) -> dict[str, object]:
    errors: list[str] = []
    try:
        workers = running_task_workers()
        worker_types = sorted(
            f"{type(worker).__module__}.{type(worker).__qualname__}"
            for worker in workers
        )
    except Exception as exc:  # noqa: BLE001 - unknown worker state must block close
        workers = None
        worker_types = []
        errors.append(f"task_worker_probe_error:{type(exc).__name__}")
    try:
        raw_research_busy = dialog.is_busy()  # type: ignore[attr-defined]
        if type(raw_research_busy) is bool:
            research_busy: bool | None = raw_research_busy
        else:
            research_busy = None
            errors.append(
                f"research_busy_probe_invalid_type:{type(raw_research_busy).__name__}"
            )
    except Exception as exc:  # noqa: BLE001 - unknown research state must block close
        research_busy = None
        errors.append(f"research_busy_probe_error:{type(exc).__name__}")
    process_running, process_id, process_error = _read_update_process_state(window)
    if process_error is not None:
        errors.append(process_error)
    is_idle = (
        workers == ()
        and research_busy is False
        and process_running is False
        and not errors
    )
    return {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "task_worker_count": len(workers) if workers is not None else None,
        "task_worker_types": worker_types,
        "research_dialog_busy": research_busy,
        "update_background_process_running": process_running,
        "update_background_process_pid": process_id,
        "probe_errors": errors,
        "idle": is_idle,
    }


def _read_after_close_state(window: object) -> dict[str, object]:
    errors: list[str] = []
    try:
        workers = running_task_workers()
        worker_types = sorted(
            f"{type(worker).__module__}.{type(worker).__qualname__}"
            for worker in workers
        )
    except Exception as exc:  # noqa: BLE001 - unknown worker state must keep polling
        workers = None
        worker_types = []
        errors.append(f"task_worker_probe_error:{type(exc).__name__}")
    process_running, process_id, process_error = _read_update_process_state(window)
    if process_error is not None:
        errors.append(process_error)
    return {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "task_worker_count": len(workers) if workers is not None else None,
        "task_worker_types": worker_types,
        "update_background_process_running": process_running,
        "update_background_process_pid": process_id,
        "probe_errors": errors,
        "idle": workers == () and process_running is False and not errors,
    }


class _ReadbackIdleCloseCoordinator:
    """等全域 worker、研究視圖與 UpdateView 外部程序皆閒置後只關閉一次。"""

    def __init__(
        self,
        window: object,
        dialog: object,
        receipt: dict[str, object],
    ) -> None:
        self._window = window
        self._dialog = dialog
        self._receipt = receipt
        self._poll_count = 0
        self.close_started = False

    def request_close_if_idle(self) -> bool:
        if self.close_started:
            return True
        self._poll_count += 1
        state = _read_close_state(self._window, self._dialog)
        self._receipt["idle_close_poll_count"] = self._poll_count
        self._receipt["idle_close_last_state"] = state
        if state["idle"] is not True:
            return False
        self.close_started = True
        self._receipt["idle_close_before_state"] = state
        self._receipt["idle_close_requests"] = _receipt_int(
            self._receipt,
            "idle_close_requests",
        ) + 1
        self._window.close()  # type: ignore[attr-defined]
        return True


def main() -> int:
    args = _parse_args()
    base_data_root = Path(args.data_root).expanduser().resolve()
    base_output_root = Path(args.output_root).expanduser().resolve()
    receipt_path = Path(args.receipt).expanduser().resolve()
    # MainWindow 會依 PROFILE 再解析一次路徑，所以環境變數保留呼叫者提供的 base。
    os.environ["DATA_ROOT"] = str(base_data_root)
    os.environ["OUTPUT_ROOT"] = str(base_output_root)

    receipt: dict[str, object] = {
        "pid": os.getpid(),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "main_window_recreated": False,
        "persisted_readback": False,
        "persisted_identity_consistent": False,
        "report_loaded": False,
        "journey_loaded": False,
        "research_workers_finished": False,
        "exact_identity_visible": False,
        "idle_close_requests": 0,
        "idle_close_poll_count": 0,
        "idle_close_before_state": None,
        "idle_close_last_state": None,
        "post_close_last_state": None,
        "main_window_close_event_count": 0,
        "watchdog_fired": False,
        "forced_termination": False,
        "app_exec_returncode": None,
        "process_exit_code": 1,
    }
    window: _ProbeMainWindow | None = None

    try:
        config = TWStockConfig(
            data_root=base_data_root,
            output_root=base_output_root,
        )
        # 唯讀讀取路徑使用 config 實際解析後的 roots，與 MainWindow 同 profile。
        data_root = Path(config.data_root).expanduser().resolve()
        output_root = Path(config.output_root).expanduser().resolve()
        read_model = build_recommendation_execution_queries(config).get(args.result_id)
        if (
            read_model is None
            or read_model.result_id != args.result_id
            or read_model.integrity_basis != "canonical_payload_and_index_verified"
            or read_model.execution is None
            or read_model.execution.result_id != args.result_id
            or read_model.execution.status is not ExecutionStatus.COMPLETED
            or read_model.execution.decision is None
        ):
            raise ValueError("saved recommendation lacks verified canonical execution")
        execution = read_model.execution

        watchlist_path = output_root / "watchlist" / "default.json"
        trades_path = output_root / "portfolio" / "trades.jsonl"
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

        recommendations = tuple(
            item for item in execution.items if item.stock_code == watch_stock_code
        )
        if len(recommendations) != 1:
            raise ValueError(
                "canonical execution lacks one exact selected item "
                f"for stock_code={watch_stock_code!r}"
            )
        recommendation = recommendations[0]
        identity = _canonical_identity_facts(execution)
        result_id = execution.result_id
        result_stock_code = recommendation.stock_code
        result_decision_date = identity["decision_date"]
        result_data_date = identity["data_date"]
        result_snapshot_id = identity["source_snapshot_id"]
        result_snapshot_hash = identity["source_snapshot_hash"]
        request_config = _request_config(execution)
        capture_projection = saved_recommendation_capture_projection(read_model)
        universe_identity = execution.context.universe_identity
        universe_snapshot = (
            universe_identity.snapshot if universe_identity is not None else None
        )
        if universe_snapshot is None:
            raise ValueError("saved execution lacks typed universe snapshot identity")
        raw_universe_spec = universe_snapshot.universe_snapshot_spec_json
        if type(raw_universe_spec) is not str:
            raise ValueError("saved universe snapshot 缺少 spec JSON 文字")
        universe_snapshot_spec = json.loads(raw_universe_spec)
        if not isinstance(universe_snapshot_spec, Mapping):
            raise ValueError("saved universe snapshot spec 必須是 JSON object")
        receipt["canonical_saved_projection"] = {
            "integrity_basis": read_model.integrity_basis,
            "execution_status": execution.status.value,
            "result_id": read_model.result_id,
            "selected_stock_code": recommendation.stock_code,
            "execution_selected_stock_codes": [
                item.stock_code for item in execution.items
            ],
            "execution_selected_count": len(execution.items),
            "universe_selected_codes": universe_snapshot_spec["selected_codes"],
            "universe_selected_count": universe_snapshot_spec["selected_count"],
            "request_source_snapshot_id": identity[
                "request_source_snapshot_id"
            ],
            "request_source_snapshot_hash": identity[
                "request_source_snapshot_hash"
            ],
            "universe_snapshot_id": identity["universe_snapshot_id"],
            "universe_snapshot_hash": identity["universe_snapshot_hash"],
            "capture": _plain(capture_projection),
        }
        trade_summary = _mapping(trade.get("source_summary"))
        expected_identity = {
            "result_id": args.result_id,
            "stock_code": result_stock_code,
            "decision_date": result_decision_date,
            "data_date": result_data_date,
            "source_snapshot_id": result_snapshot_id,
            "source_snapshot_hash": result_snapshot_hash,
            "universe_snapshot_id": identity["universe_snapshot_id"],
            "universe_snapshot_hash": identity["universe_snapshot_hash"],
            "recommendation_source_snapshot_id": identity[
                "request_source_snapshot_id"
            ],
            "recommendation_source_snapshot_hash": identity[
                "request_source_snapshot_hash"
            ],
        }
        context = ResearchStockContextDTO(
            stock_code=_text(watch_identity, "stock_code") or result_stock_code,
            stock_name=(
                _text(watch_item, "stock_name") or recommendation.stock_name or ""
            ),
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
            source_id=_text(watch_item, "source_id") or _text(request_config, "source_id"),
            source_kind=_text(request_config, "source_kind") or "persisted_recommendation",
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
            "source_snapshot_hash": _text(trade_summary, "source_snapshot_hash"),
            "summary_checksum": _text(trade, "source_snapshot_hash"),
            "summary_checksum_verified": (
                _text(trade, "source_snapshot_hash")
                == stable_snapshot_hash(trade_summary)
            ),
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
            and trade_readback["result_id"] == expected_identity["result_id"]
            and trade_readback["stock_code"] == expected_identity["stock_code"]
            and trade_readback["decision_date"] == expected_identity["decision_date"]
            and trade_readback["source_snapshot_id"]
            == expected_identity["source_snapshot_id"]
            and trade_readback["source_snapshot_hash"]
            == expected_identity["source_snapshot_hash"]
            and trade_readback["summary_checksum_verified"] is True
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
            "recommendation_source_snapshot": {
                "source_snapshot_id": identity[
                    "request_source_snapshot_id"
                ],
                "source_snapshot_hash": identity[
                    "request_source_snapshot_hash"
                ],
            },
            "universe_snapshot": {
                "universe_snapshot_id": identity["universe_snapshot_id"],
                "universe_snapshot_hash": identity["universe_snapshot_hash"],
            },
        }

        app = QApplication.instance() or QApplication(sys.argv)
        window = _ProbeMainWindow()
        receipt["main_window_recreated"] = isinstance(window, MainWindow)
        window.show()
        window._open_stock_research_context(context)
        dialog = window.stock_research_workspace
        if dialog is None:
            raise RuntimeError("MainWindow did not create StockResearchWorkspace")

        report_loaded = False
        journey_loaded = False
        close_coordinator = _ReadbackIdleCloseCoordinator(window, dialog, receipt)

        def finish_after_close() -> None:
            post_close_state = _read_after_close_state(window)
            receipt["post_close_last_state"] = post_close_state
            if _not_visible(window) and post_close_state["idle"] is True:
                app.quit()
            else:
                QTimer.singleShot(20, finish_after_close)

        def mark_research_workers_finished() -> None:
            receipt["research_workers_finished"] = not dialog.is_busy()

        app.aboutToQuit.connect(mark_research_workers_finished)

        def finish_when_both_views_loaded() -> None:
            if close_coordinator.close_started or not report_loaded or not journey_loaded:
                return
            if not close_coordinator.request_close_if_idle():
                QTimer.singleShot(20, finish_when_both_views_loaded)
                return
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
            linked_trades = tuple(
                item
                for item in getattr(journey, "portfolio_trades", ())
                if getattr(item, "source_id", None) == context.result_id
                and getattr(item, "stock_code", None) == context.stock_code
            )
            controls = journey_view.continuity_controls
            controls_identity = getattr(controls, "identity", None)
            controls_state = getattr(controls, "state", None)
            rendered = receipt.setdefault("rendered_identity", {})
            if not isinstance(rendered, dict):
                rendered = {}
                receipt["rendered_identity"] = rendered
            rendered["journey"] = {
                "status": str(getattr(journey, "status", "")),
                "result_id": getattr(result_record, "result_id", ""),
                "result_link_status": str(
                    getattr(result_record, "link_status", "")
                ),
                "candidate_key": list(getattr(candidate, "candidate_key", ()) or ()),
                "candidate_found": candidate is not None,
                "portfolio_trade_count": len(linked_trades),
                "portfolio_trade_link_statuses": [
                    str(getattr(item, "link_status", ""))
                    for item in linked_trades
                ],
                "decision_date": getattr(result_record, "decision_date", ""),
                "source_snapshot_id": getattr(
                    source_identity, "source_snapshot_id", None
                )
                or "",
                "source_snapshot_hash": getattr(
                    source_identity, "source_snapshot_hash", None
                )
                or "",
                "universe_snapshot_id": getattr(
                    source_identity,
                    "universe_snapshot_id",
                    "",
                ),
                "universe_snapshot_hash": getattr(
                    source_identity,
                    "universe_snapshot_hash",
                    "",
                ),
                "maturity_rows": [
                    {
                        "window_days": getattr(item, "window_days", None),
                        "link_status": str(getattr(item, "status", "")),
                        "outcome_status": getattr(item, "outcome_status", ""),
                    }
                    for item in maturity
                ],
                "diagnostics": [
                    {
                        "code": getattr(item, "code", ""),
                        "detail": getattr(item, "detail", ""),
                        "severity": getattr(item, "severity", ""),
                    }
                    for item in getattr(journey, "diagnostics", ())
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
                and len(linked_trades) == 1
                and getattr(
                    getattr(linked_trades[0], "link_status", None), "value", None
                ) == "linked"
                and source_identity is not None
                and getattr(source_identity, "decision_date", "")
                == expected_identity["decision_date"]
                and (getattr(source_identity, "source_snapshot_id", None) or "")
                == expected_identity["recommendation_source_snapshot_id"]
                and (getattr(source_identity, "source_snapshot_hash", None) or "")
                == expected_identity["recommendation_source_snapshot_hash"]
                and getattr(source_identity, "universe_snapshot_id", "")
                == expected_identity["universe_snapshot_id"]
                and getattr(source_identity, "universe_snapshot_hash", "")
                == expected_identity["universe_snapshot_hash"]
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
        final_close_state = _read_after_close_state(window)
        receipt["post_close_last_state"] = final_close_state
        receipt["remaining_workers_after_exec"] = final_close_state["task_worker_count"]
        receipt["update_background_process_running_after_exec"] = final_close_state[
            "update_background_process_running"
        ]
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
            == expected_identity["recommendation_source_snapshot_id"]
            and journey_identity.get("source_snapshot_hash")
            == expected_identity["recommendation_source_snapshot_hash"]
            and journey_identity.get("universe_snapshot_id")
            == expected_identity["universe_snapshot_id"]
            and journey_identity.get("universe_snapshot_hash")
            == expected_identity["universe_snapshot_hash"]
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
            and receipt["research_workers_finished"] is True
            and receipt["idle_close_requests"] == 1
            and receipt["main_window_close_event_count"] == 1
            and receipt["journey_loaded"] is True
            and receipt["exact_identity_visible"] is True
            and receipt["watchdog_fired"] is False
            and receipt["forced_termination"] is False
            and receipt["window_hidden_after_exec"] is True
            and receipt["remaining_workers_after_exec"] == 0
            and receipt["update_background_process_running_after_exec"] is False
            and app_exec_returncode == 0
            else 1
        )
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if window is not None:
            cleanup_app = QApplication.instance()
            if isinstance(cleanup_app, QApplication):
                try:
                    _drain_qt_deferred_deletes(cleanup_app, (window,))
                except (RuntimeError, TypeError):
                    pass
            receipt["main_window_close_event_count"] = window.close_event_count
        receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return _receipt_int(receipt, "process_exit_code")


if __name__ == "__main__":
    raise SystemExit(main())
