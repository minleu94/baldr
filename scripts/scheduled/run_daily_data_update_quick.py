from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_module.update_service import UpdateService
from app_module.update_status_history import append_update_status_history
from data_module.config import TWStockConfig
from data_module.official_trading_calendar import (
    OfficialTradingCalendar,
    OfficialTradingCalendarError,
)
from data_module.ml_storage_capacity import (
    BYTES_PER_GIB,
    HEAVY_CHAIN_LOCK_FILENAME,
    StorageCapacityError,
    acquire_heavy_chain_reservation,
    heavy_chain_capacity_budget,
    preflight_capacity,
    release_heavy_chain_reservation,
)
from data_module.phase3c_backfill_runner import configured_candidate_db_path
from scripts.scheduled.scheduled_clock import scheduled_now


StepAction = Callable[[], dict[str, Any]]


def _parse_date(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text[:8], fmt)
        except ValueError:
            continue
    return None


def _calendar_records_for_window(
    reference_date: date,
    days: int,
    *,
    calendar: OfficialTradingCalendar | None = None,
) -> list[dict[str, Any]]:
    resolver = calendar or OfficialTradingCalendar(
        calendar_cache_path=_default_calendar_cache_path(),
    )
    return resolver.get_recent_official_trading_days(
        reference_date,
        max(1, int(days)),
        include_reference=True,
        allow_online_probe=True,
    )


def _scheduled_target_weekday(
    today: date,
    calendar: OfficialTradingCalendar | None = None,
) -> date:
    """Compatibility name for the latest official session selector."""

    records = _calendar_records_for_window(today, 1, calendar=calendar)
    return date.fromisoformat(str(records[-1]["date_str"]))


def _weekday_window(
    end_day: date,
    days: int,
    calendar: OfficialTradingCalendar | None = None,
) -> tuple[str, str]:
    """Compatibility name for an official-calendar update window."""

    records = _calendar_records_for_window(end_day, days, calendar=calendar)
    return str(records[0]["date_str"]), str(records[-1]["date_str"])


def _serializable_calendar_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in record.items() if key != "date"}
        for record in records
    ]


def _default_calendar_cache_path() -> Path | None:
    """Use the existing immutable official-calendar cache when available."""

    path = REPO_ROOT / "output" / "paper_execution_eod_replay" / "calendar_cache"
    return path if path.is_dir() else None


def _json_safe(value: Any, *, _seen: set[int] | None = None) -> Any:
    """Convert service results into a bounded JSON-compatible status value.

    Scheduled service results are allowed to carry dataclasses (for example the
    Phase 3C ``BackfillSummary``), ``Path`` instances, dates, or scalar wrapper
    types.  Those values are useful in a status payload but must not be able to
    prevent publication of the terminal run status.  Unknown values are kept as
    a diagnostic representation instead of raising from the status writer.
    """

    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return _json_safe(value.value, _seen=_seen)
    if isinstance(value, Path):
        return str(value)

    seen = _seen if _seen is not None else set()
    object_id = id(value)
    if object_id in seen:
        return f"<circular:{type(value).__name__}>"
    seen.add(object_id)
    try:
        if is_dataclass(value) and not isinstance(value, type):
            try:
                return _json_safe(asdict(value), _seen=seen)
            except Exception:  # noqa: BLE001
                pass
        if isinstance(value, Mapping):
            return {
                str(key): _json_safe(child, _seen=seen)
                for key, child in value.items()
            }
        if isinstance(value, (list, tuple, set, frozenset)):
            return [_json_safe(child, _seen=seen) for child in value]
        for method_name in ("as_dict", "to_dict"):
            method = getattr(value, method_name, None)
            if callable(method):
                try:
                    converted = method()
                except Exception:  # noqa: BLE001
                    continue
                if converted is not value:
                    return _json_safe(converted, _seen=seen)
        item = getattr(value, "item", None)
        if callable(item):
            try:
                converted = item()
            except Exception:  # noqa: BLE001
                converted = value
            if converted is not value:
                return _json_safe(converted, _seen=seen)
        return repr(value)
    finally:
        seen.discard(object_id)


def _json_safe_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    converted = _json_safe(payload)
    if not isinstance(converted, dict):
        raise TypeError("scheduled status payload must serialize to an object")
    return converted


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_payload = _json_safe_payload(payload)
    path.write_text(
        json.dumps(safe_payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _append_history_safely(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """保存 append-only history；history 寫入失敗不掩蓋主要更新結果。"""

    try:
        return append_update_status_history(path, _json_safe_payload(payload))
    except Exception as exc:  # noqa: BLE001
        logging.warning("Unable to append data update history: %s", exc)
        return {
            "appended": False,
            "duplicate": False,
            "path": str(path),
            "error": f"{type(exc).__name__}:{exc}",
        }


def _setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)


def _step_payload(name: str, result: dict[str, Any], warning: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "status": "warning" if warning else "passed" if result.get("success", True) else "failed",
        "message": result.get("message", ""),
        "result": result,
    }


def _tpex_warning_messages(result: dict[str, Any]) -> list[str]:
    messages = [str(item) for item in result.get("warnings", []) if str(item).strip()]
    failed_dates = sorted({str(item) for item in result.get("failed_dates", []) if str(item).strip()})
    if failed_dates:
        messages.append(f"TPEX 每日股價缺少日期：{', '.join(failed_dates)}")
    return list(dict.fromkeys(messages))


def _twse_skip_warning_messages(result: dict[str, Any]) -> list[str]:
    skipped_dates = sorted(
        {
            str(item)
            for item in result.get("no_data_skipped_dates", [])
            if str(item).strip()
        }
    )
    if not skipped_dates:
        return []
    return [f"TWSE 官方無交易資料日（休市／颱風等），已略過日期：{', '.join(skipped_dates)}"]


def _update_market_with_capture(
    service: Any, start_date: str, end_date: str, capture_manifests: list[Path],
) -> dict[str, Any]:
    """支援舊 service double，同時傳遞本次 TWSE capture sink。"""
    import inspect

    update_market = service.update_market
    parameters = inspect.signature(update_market).parameters
    if "capture_manifests" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    ):
        return update_market(
            start_date,
            end_date,
            capture_manifests=capture_manifests,
        )
    return update_market(start_date, end_date)


def _sync_market_index_for_run(
    service: Any,
    *,
    capture_manifests: list[Path],
    market_update_result: Any,
) -> dict[str, Any]:
    """實際服務走 TAIEX 複合鍵發布；舊 service double 保留原同步介面。"""
    publisher = getattr(service, "publish_taiex_market_index", None)
    if callable(publisher):
        return publisher(
            capture_manifests=capture_manifests,
            market_update_result=(
                market_update_result
                if isinstance(market_update_result, dict)
                else {"success": False}
            ),
        )
    return service.sync_source_to_sqlite("market_index")


def _run_step(
    *,
    steps: list[dict[str, Any]],
    name: str,
    action: StepAction,
    warning_only: bool = False,
) -> dict[str, Any] | None:
    logging.info("Starting step: %s", name)
    try:
        result = action()
    except Exception as exc:  # noqa: BLE001
        # Scheduled execution must publish a terminal status and release its
        # shared capacity reservation even when a service raises unexpectedly.
        result = {
            "success": False,
            "error_type": type(exc).__name__,
            "message": f"{type(exc).__name__}: {exc}",
        }
    ok = bool(result.get("success", True))
    if not ok and warning_only:
        logging.warning("Step completed with warning: %s: %s", name, result.get("message", ""))
        steps.append(_step_payload(name, result, warning=True))
        return None
    steps.append(_step_payload(name, result))
    if not ok:
        logging.error("Step failed: %s: %s", name, result.get("message", ""))
        return result
    logging.info("Step passed: %s", name)
    return None


def _sync_daily_price_files_with_twse_evidence(
    service: Any,
    *,
    steps: list[dict[str, Any]],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """只把本次 TWSE subprocess 明確回報的 projection 傳給 SQLite publisher。"""

    twse_result: dict[str, Any] = {}
    for step in steps:
        result = step.get("result")
        if step.get("name") == "update_twse_daily_prices" and isinstance(result, dict):
            twse_result = result
            break
    diagnostics = twse_result.get("source_diagnostics", [])
    if not isinstance(diagnostics, list):
        diagnostics = []
    trusted_diagnostics = [
        item for item in diagnostics if isinstance(item, dict)
    ]
    return service.sync_source_to_sqlite(
        "daily_price_files",
        start_date,
        end_date,
        row_evidence_source_diagnostics=trusted_diagnostics,
    )


def _technical_is_current(
    status: dict[str, Any],
    coverage: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    if coverage and coverage.get("success") and not coverage.get("is_current", True):
        covered = coverage.get("covered_stock_count", 0)
        eligible = coverage.get("eligible_stock_count", 0)
        latest = coverage.get("daily_latest_date") or "latest daily date"
        return False, f"technical coverage lagging at {latest}: {covered}/{eligible}"

    daily_latest = _parse_date((status.get("daily_data") or {}).get("latest_date"))
    technical_latest = _parse_date((status.get("technical_indicators") or {}).get("latest_date"))
    if daily_latest is not None and technical_latest is not None and technical_latest >= daily_latest:
        return True, f"technical indicators current at {technical_latest.strftime('%Y-%m-%d')}"
    return False, ""


def _annotate_currentity_recompute_outcome(
    calculation: dict[str, Any],
) -> dict[str, Any]:
    """保留部分成功數量，並用可區分的代碼描述 currentity 重算結果。"""

    success_count = int(calculation.get("success_count") or 0)
    updated_stocks = calculation.get("updated_stocks")
    updated = (
        [str(item) for item in updated_stocks if str(item).strip()]
        if isinstance(updated_stocks, list)
        else []
    )
    failed_stocks_value = calculation.get("failed_stocks")
    failed_stocks = (
        [str(item) for item in failed_stocks_value if str(item).strip()]
        if isinstance(failed_stocks_value, list)
        else []
    )
    fail_count = max(
        int(calculation.get("fail_count") or 0),
        len(set(failed_stocks)),
    )

    if calculation.get("cancelled") is True:
        error_code = "technical_currentity_recompute_cancelled"
    elif success_count > 0 and updated and (fail_count > 0 or failed_stocks):
        error_code = "technical_currentity_recompute_partial_failure"
    elif success_count > 0 and updated and calculation.get("sqlite_write_failed") is True:
        error_code = "technical_currentity_recompute_sqlite_write_failed"
    elif success_count <= 0 or not updated:
        error_code = "technical_currentity_recompute_produced_no_updates"
    elif calculation.get("success") is not True:
        error_code = "technical_currentity_recompute_failed"
    else:
        return calculation

    calculation["success"] = False
    calculation["technical_computation_error"] = error_code
    details = [f"updated={success_count}"]
    if fail_count:
        details.append(f"failed={fail_count}")
    if failed_stocks:
        details.append(f"failed_stocks={','.join(failed_stocks)}")
    message = str(calculation.get("message") or "").strip()
    diagnostic = f"{error_code} ({', '.join(details)})"
    calculation["message"] = f"{message}; {diagnostic}" if message else diagnostic
    return calculation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run scheduled baldr quick data update.")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument(
        "--formal-output-root",
        help=(
            "explicit formal output root whose existing verified technical "
            "receipts may be reused; defaults to <data-root>/output"
        ),
    )
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--window-weekdays", type=int, default=10)
    parser.add_argument("--daily-delay-seconds", type=float, default=0.5)
    parser.add_argument("--tpex-delay-seconds", type=float, default=0.5)
    parser.add_argument("--broker-delay-seconds", type=float, default=0.5)
    parser.add_argument(
        "--skip-broker-branch",
        action="store_true",
        help=(
            "skip the optional MoneyDJ broker-branch refresh so the bounded "
            "official price/index/technical source path can complete"
        ),
    )
    parser.add_argument("--status-path")
    parser.add_argument(
        "--history-path",
        help="append-only JSONL history path; defaults beside --status-path",
    )
    parser.add_argument("--log-path")
    parser.add_argument(
        "--capacity-persistent-new-gib",
        type=int,
        default=1,
        help="本次更新允許的持久新增 GiB 上限；仍保留中央 200 GiB 安全底線",
    )
    parser.add_argument(
        "--capacity-temporary-peak-gib",
        type=int,
        default=1,
        help="本次更新允許的暫存峰值 GiB 上限；仍保留中央 200 GiB 安全底線",
    )
    parser.add_argument(
        "--capacity-lock-path",
        help=(
            "跨每日更新與 Raw/Direct/OOC heavy chain 共用的 reservation lock；"
            "省略時使用 output-root/release_v4/.ml_heavy_chain.lock"
        ),
    )
    parser.add_argument(
        "--enable-technical-process-pool",
        action="store_true",
        help=(
            "explicitly enable bounded technical-indicator workers for this run; "
            "default remains serial and parent-only"
        ),
    )
    parser.add_argument("--technical-process-pool-workers", type=int)
    parser.add_argument("--technical-process-pool-max-in-flight", type=int)
    parser.add_argument("--technical-process-pool-max-retries", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_root = Path(args.output_root).expanduser().resolve()
    formal_output_root = (
        Path(args.formal_output_root).expanduser().resolve()
        if args.formal_output_root
        else (Path(args.data_root).expanduser().resolve() / "output")
    )
    authorized_technical_output_roots = tuple(
        dict.fromkeys((output_root, formal_output_root))
    )
    run_root = output_root / "scheduled" / "data_update_quick"
    run_now = scheduled_now()
    run_date = run_now.date()
    today_key = run_date.strftime("%Y%m%d")
    status_path = Path(args.status_path) if args.status_path else run_root / "latest_status.json"
    history_path = (
        Path(args.history_path)
        if args.history_path
        else status_path.parent / "history.jsonl"
    )
    log_path = Path(args.log_path) if args.log_path else run_root / f"{today_key}_data_update_quick.log"
    _setup_logging(log_path)

    capacity_preflight: dict[str, Any] | None = None
    candidate_db_path = configured_candidate_db_path()
    capacity_lock_path = Path(args.capacity_lock_path) if args.capacity_lock_path else (
        output_root / "release_v4" / HEAVY_CHAIN_LOCK_FILENAME
    )
    capacity_reservation = None
    try:
        # 先取得與 Raw／Direct／OOC 相同的 OS reservation，再量測容量。
        # 只做 free-space check 而不持有 reservation，兩個同時啟動的
        # caller 可能各自通過而共同耗盡 D 槽 headroom。
        capacity_reservation = acquire_heavy_chain_reservation(capacity_lock_path)
        if capacity_reservation is None:
            raise StorageCapacityError(
                "shared capacity reservation is already held by another process",
                preflight={
                    "stage": "scheduled_daily_update_reservation",
                    "lock_path": str(capacity_lock_path),
                    "blocker": "shared_capacity_reservation_unavailable",
                },
            )
        capacity_budget = heavy_chain_capacity_budget(
            persistent_new_bytes_budget=(
                int(args.capacity_persistent_new_gib) * BYTES_PER_GIB
            ),
            temporary_peak_bytes_budget=(
                int(args.capacity_temporary_peak_gib) * BYTES_PER_GIB
            ),
        )
        persistent_root_candidates = (
            Path(args.data_root),
            output_root,
            candidate_db_path.parent if candidate_db_path is not None else None,
            capacity_lock_path.parent,
        )
        persistent_roots = tuple(
            dict.fromkeys(
                path for path in persistent_root_candidates if path is not None
            )
        )
        capacity_result = preflight_capacity(
            probe_path=Path(args.data_root),
            budget=capacity_budget,
            stage="scheduled_daily_update_preflight",
            persistent_roots=persistent_roots,
            persistent_new_bytes_estimate=capacity_budget.persistent_new_bytes_budget,
            # The scheduled data root is the protected production volume.  A
            # caller that places temporary files on another volume can pass
            # that root to the shared preflight service directly; this runner
            # avoids probing a packaged-app temp extraction path that may be
            # unreadable on Windows.
            temporary_roots=(),
            temporary_peak_bytes_observed=capacity_budget.temporary_peak_bytes_budget,
        )
        capacity_preflight = capacity_result.as_dict()
    except Exception as exc:  # noqa: BLE001
        # Capacity is a fail-closed gate.  Do not start a network download or
        # SQLite writer if the filesystem cannot prove the required reserve.
        completed_at = scheduled_now()
        failure_message = f"capacity_preflight_failed:{type(exc).__name__}:{exc}"
        failure_payload = {
            "task": "baldr-data-update-quick-daily",
            "status": "failed",
            "run_id": f"{today_key}-{os.getpid()}",
            "started_at": run_now.isoformat(),
            "completed_at": completed_at.isoformat(),
            "checked_at": completed_at.isoformat(),
            "process_id": os.getpid(),
            "data_root": str(args.data_root),
            "output_root": str(output_root),
            "formal_output_root": str(formal_output_root),
            "authorized_technical_output_roots": [
                str(path) for path in authorized_technical_output_roots
            ],
            "candidate_db_path": str(candidate_db_path) if candidate_db_path else None,
            "capacity_lock_path": str(capacity_lock_path),
            "capacity_reservation_acquired": False,
            "calendar_resolution": [],
            "steps": [],
            "warnings": [],
            "errors": [failure_message],
            "capacity_preflight": getattr(exc, "preflight", None),
            "writes_market_data_db": False,
            "writes_evidence_db": False,
            "auto_trading": False,
            "auto_lifecycle_action": False,
            "history_path": str(history_path),
        }
        failure_payload["history"] = _append_history_safely(history_path, failure_payload)
        _write_json(status_path, failure_payload)
        logging.error(failure_message)
        release_heavy_chain_reservation(capacity_reservation)
        capacity_reservation = None
        return 2

    config = TWStockConfig(
        data_root=Path(args.data_root),
        output_root=output_root,
        technical_process_pool_enabled=bool(args.enable_technical_process_pool),
    )
    if args.technical_process_pool_workers is not None:
        config.technical_process_pool_workers = args.technical_process_pool_workers
    if args.technical_process_pool_max_in_flight is not None:
        config.technical_process_pool_max_in_flight = args.technical_process_pool_max_in_flight
    if args.technical_process_pool_max_retries is not None:
        config.technical_process_pool_max_retries = args.technical_process_pool_max_retries

    calendar = OfficialTradingCalendar(
        db_path=config.db_file,
        calendar_cache_path=_default_calendar_cache_path(),
    )
    calendar_records: list[dict[str, Any]] = []
    try:
        if args.start_date and args.end_date:
            start_date = args.start_date
            end_date = args.end_date
            calendar_records = calendar.require_trading_days_in_range(
                date.fromisoformat(start_date),
                date.fromisoformat(end_date),
                allow_online_probe=True,
            )
        else:
            calendar_records = _calendar_records_for_window(
                run_date,
                max(1, args.window_weekdays),
                calendar=calendar,
            )
            start_date = str(calendar_records[0]["date_str"])
            end_date = str(calendar_records[-1]["date_str"])
    except (OfficialTradingCalendarError, ValueError) as exc:
        completed_at = scheduled_now()
        failure_message = f"official_trading_calendar_unavailable:{type(exc).__name__}:{exc}"
        failure_payload = {
            "task": "baldr-data-update-quick-daily",
            "status": "failed",
            "run_id": f"{today_key}-{os.getpid()}",
            "started_at": run_now.isoformat(),
            "completed_at": completed_at.isoformat(),
            "checked_at": completed_at.isoformat(),
            "process_id": os.getpid(),
            "data_root": str(config.data_root),
            "output_root": str(config.output_root),
            "formal_output_root": str(formal_output_root),
            "authorized_technical_output_roots": [
                str(path) for path in authorized_technical_output_roots
            ],
            "candidate_db_path": str(candidate_db_path) if candidate_db_path else None,
            "start_date": args.start_date,
            "end_date": args.end_date,
            "capacity_lock_path": str(capacity_lock_path),
            "capacity_reservation_acquired": False,
            "calendar_resolution": [],
            "steps": [],
            "warnings": [],
            "errors": [failure_message],
            "capacity_preflight": capacity_preflight,
            "writes_market_data_db": False,
            "writes_evidence_db": False,
            "auto_trading": False,
            "auto_lifecycle_action": False,
            "history_path": str(history_path),
        }
        failure_payload["history"] = _append_history_safely(history_path, failure_payload)
        _write_json(status_path, failure_payload)
        logging.error(failure_message)
        release_heavy_chain_reservation(capacity_reservation)
        capacity_reservation = None
        return 1

    service = UpdateService(config)
    steps: list[dict[str, Any]] = []
    warnings: list[str] = []
    failed: dict[str, Any] | None = None
    market_capture_manifests: list[Path] = []

    logging.info("Scheduled quick data update window: %s to %s", start_date, end_date)

    run_id = f"{today_key}-{os.getpid()}"
    running_payload = {
        "task": "baldr-data-update-quick-daily",
        "status": "running",
        "run_id": run_id,
        "started_at": run_now.isoformat(),
        "process_id": os.getpid(),
        "data_root": str(config.data_root),
        "output_root": str(config.output_root),
        "formal_output_root": str(formal_output_root),
        "authorized_technical_output_roots": [
            str(path) for path in authorized_technical_output_roots
        ],
        "candidate_db_path": str(candidate_db_path) if candidate_db_path else None,
        "capacity_lock_path": str(capacity_lock_path),
        "capacity_reservation_acquired": capacity_reservation is not None,
        "start_date": start_date,
        "end_date": end_date,
        "calendar_resolution": _serializable_calendar_records(calendar_records),
        "log_path": str(log_path),
        "steps": [],
        "warnings": [],
        "errors": [],
        "writes_market_data_db": True,
        "writes_evidence_db": False,
        "auto_trading": False,
        "auto_lifecycle_action": False,
        "history_path": str(history_path),
        "technical_process_pool_enabled": config.technical_process_pool_enabled,
        "technical_process_pool_workers": config.technical_process_pool_workers,
        "technical_process_pool_max_in_flight": config.technical_process_pool_max_in_flight,
        "technical_process_pool_max_retries": config.technical_process_pool_max_retries,
        "capacity_preflight": capacity_preflight,
        "optional_source_policy": {
            "skip_broker_branch": bool(args.skip_broker_branch),
        },
    }
    _write_json(status_path, running_payload)
    running_payload["history"] = _append_history_safely(history_path, running_payload)
    _write_json(status_path, running_payload)

    failed = _run_step(steps=steps, name="check_overview_before", action=service.check_data_overview)
    if failed is None:
        failed = _run_step(
            steps=steps,
            name="update_twse_daily_prices",
            action=lambda: service.update_daily(start_date, end_date, delay_seconds=args.daily_delay_seconds),
        )
    if failed is None:
        failed = _run_step(
            steps=steps,
            name="update_tpex_daily_prices",
            action=lambda: service.update_tpex_daily_price_range(
                start_date,
                end_date,
                delay_seconds=args.tpex_delay_seconds,
                force_refresh=False,
                sync_to_sqlite=False,
                break_on_repeated_source_date=False,
                twse_no_data_dates=next((s["result"].get("no_data_skipped_dates", []) for s in steps if s["name"] == "update_twse_daily_prices"), []),
            ),
            warning_only=True,
        )
    if failed is None:
        failed = _run_step(
            steps=steps,
            name="sync_daily_prices_to_sqlite",
            action=lambda: _sync_daily_price_files_with_twse_evidence(
                service,
                steps=steps,
                start_date=start_date,
                end_date=end_date,
            ),
        )
    if failed is None:
        failed = _run_step(
            steps=steps,
            name="update_market_index",
            action=lambda: _update_market_with_capture(
                service,
                start_date,
                end_date,
                market_capture_manifests,
            ),
        )
    if failed is None:
        market_update_result: Any = next(
            (
                step.get("result")
                for step in steps
                if step.get("name") == "update_market_index"
            ),
            {},
        )
        failed = _run_step(
            steps=steps,
            name="sync_market_index_to_sqlite",
            action=lambda: _sync_market_index_for_run(
                service,
                capture_manifests=market_capture_manifests,
                market_update_result=market_update_result,
            ),
        )
    if failed is None:
        failed = _run_step(steps=steps, name="update_industry_index", action=lambda: service.update_industry(start_date, end_date))
    if failed is None:
        failed = _run_step(steps=steps, name="sync_industry_index_to_sqlite", action=lambda: service.sync_source_to_sqlite("industry_index"))
    if failed is None and args.skip_broker_branch:
        steps.extend(
            [
                {
                    "name": "update_broker_branch",
                    "status": "skipped",
                    "message": "optional broker-branch source skipped by explicit bounded-run policy",
                    "result": {
                        "success": True,
                        "skipped": True,
                        "optional_source": True,
                        "reason": "explicit_skip_broker_branch",
                    },
                },
                {
                    "name": "sync_broker_branch_to_sqlite",
                    "status": "skipped",
                    "message": "broker-branch sync skipped because its optional source refresh was skipped",
                    "result": {
                        "success": True,
                        "skipped": True,
                        "optional_source": True,
                        "reason": "broker_branch_refresh_skipped",
                    },
                },
            ]
        )
    if failed is None and not args.skip_broker_branch:
        failed = _run_step(
            steps=steps,
            name="update_broker_branch",
            action=lambda: service.update_broker_branch(start_date, end_date, delay_seconds=args.broker_delay_seconds),
        )
    if failed is None and not args.skip_broker_branch:
        failed = _run_step(
            steps=steps,
            name="sync_broker_branch_to_sqlite",
            action=lambda: service.sync_source_to_sqlite("broker_branch_files", start_date, end_date),
        )
    if failed is None:
        candidate_updater = getattr(service, "update_phase3c_candidate_range", None)
        if candidate_db_path is None or not callable(candidate_updater):
            steps.append(
                {
                    "name": "update_phase3c_candidate_sources",
                    "status": "skipped",
                    "message": "未設定候選資料庫路徑；保留正式資料更新，未猜測候選寫入位置",
                    "result": {
                        "success": True,
                        "skipped": True,
                        "candidate_only": True,
                        "reason": "candidate_db_path_not_configured",
                    },
                }
            )
        else:
            failed = _run_step(
                steps=steps,
                name="update_phase3c_candidate_sources",
                action=lambda: candidate_updater(
                    start_date=start_date,
                    end_date=end_date,
                    sources=("institutional", "credit"),
                    include_latest_tdcc_snapshot=run_date.weekday() == 0,
                    allow_online_calendar_probe=True,
                    progress_callback=None,
                ),
                warning_only=True,
            )
    if failed is None:
        status = service.check_data_overview()
        coverage = service.check_technical_indicator_latest_coverage()
        current, message = _technical_is_current(status, coverage)
        def _calculate_technical_with_evidence(
            *,
            recompute_currentity: bool = False,
        ) -> dict[str, Any]:
            """Run the real calculator and attach a pre/post hash witness."""

            from data_module.recommendation_calibration_source_contract import (
                build_technical_computation_evidence,
                capture_technical_input_snapshot,
                daily_price_receipt_source_dates,
                discover_daily_price_receipt_paths,
            )

            receipt_path_set: set[Path] = set()
            for receipt_root in authorized_technical_output_roots:
                receipt_path_set.update(
                    discover_daily_price_receipt_paths(
                        receipt_root,
                        values=steps,
                        source_date_start=start_date,
                        source_date_end=end_date,
                    )
                )
            receipt_paths = sorted(receipt_path_set)
            receipt_dates = daily_price_receipt_source_dates(receipt_paths)
            evidence_start = receipt_dates[0] if receipt_dates else start_date
            evidence_end = receipt_dates[-1] if receipt_dates else end_date
            started_at = datetime.now(timezone.utc)
            input_snapshot = capture_technical_input_snapshot(
                config.db_file,
            )
            calculation = service.calculate_technical_indicators(
                target_stock=None,
                force_all=False,
                start_date=None,
                progress_callback=None,
                incremental_lookback_days=120,
                recompute_currentity=recompute_currentity,
                technical_process_pool=config.technical_process_pool_enabled,
                technical_process_pool_workers=config.technical_process_pool_workers,
                technical_process_pool_max_in_flight=config.technical_process_pool_max_in_flight,
                technical_process_pool_max_retries=config.technical_process_pool_max_retries,
            )
            completed_at = datetime.now(timezone.utc)
            calculation = dict(calculation)
            calculation["source_receipts"] = [
                {"receipt_path": str(path)} for path in receipt_paths
            ]
            if recompute_currentity:
                calculation["technical_recomputation_mode"] = (
                    "bounded_currentity_recompute"
                )
                calculation["technical_recomputation_lookback_days"] = 120
                calculation = _annotate_currentity_recompute_outcome(calculation)
            if calculation.get("success") is True:
                if input_snapshot.get("verified") is True:
                    try:
                        calculation["technical_computation"] = (
                            build_technical_computation_evidence(
                                source_db=config.db_file,
                                calculation_result=calculation,
                                source_date_start=evidence_start,
                                source_date_end=evidence_end,
                                started_at=started_at,
                                completed_at=completed_at,
                                input_snapshot=input_snapshot,
                            )
                        )
                    except Exception as exc:  # noqa: BLE001
                        calculation["technical_computation_error"] = (
                            f"{type(exc).__name__}:{exc}"
                        )
                        calculation["success"] = False
                else:
                    calculation["technical_computation_error"] = str(
                        input_snapshot.get("reason") or "technical_input_snapshot_unverified"
                    )
                    calculation["success"] = False
            return calculation

        if current:
            from data_module.recommendation_calibration_source_contract import (
                reuse_verified_technical_computation_receipt,
            )

            reuse = reuse_verified_technical_computation_receipt(
                authorized_output_roots=authorized_technical_output_roots,
                source_db=config.db_file,
                source_date_start=start_date,
                source_date_end=end_date,
                availability_cutoff_at=run_now,
            )
            if reuse.get("status") == "reused":
                technical_computation = reuse.get("technical_computation")
                source_publication_receipt = reuse.get("source_publication_receipt")
                if not isinstance(technical_computation, Mapping) or not isinstance(
                    source_publication_receipt, Mapping
                ):
                    reuse["status"] = "not_found"
                    reuse["reason"] = "technical_reuse_result_shape_invalid"
                else:
                    steps.append(
                        {
                            "name": "calculate_technical_indicators",
                            "status": "skipped",
                            "message": (
                                f"{message}; reused verified technical computation witness"
                            ),
                            "result": {
                                "success": True,
                                "skipped": True,
                                "skip_reason": "technical_indicators_current",
                                "technical_computation": dict(technical_computation),
                                "technical_computation_reuse": dict(
                                    source_publication_receipt
                                ),
                                "technical_reuse_validation": {
                                    "status": "reused",
                                    "source_date_start": reuse.get("source_date_start"),
                                    "source_date_end": reuse.get("source_date_end"),
                                },
                            },
                        }
                    )
                    logging.info(
                        "%s; reused verified technical computation witness from %s",
                        message,
                        source_publication_receipt.get("path"),
                    )
            if not steps or steps[-1].get("name") != "calculate_technical_indicators":
                logging.info(
                    "%s; no reusable verified witness (%s), running bounded recomputation",
                    message,
                    reuse.get("reason") or "unknown",
                )
                failed = _run_step(
                    steps=steps,
                    name="calculate_technical_indicators",
                    action=lambda: _calculate_technical_with_evidence(
                        recompute_currentity=True
                    ),
                )
        else:
            failed = _run_step(
                steps=steps,
                name="calculate_technical_indicators",
                action=_calculate_technical_with_evidence,
            )
    if failed is None:
        failed = _run_step(steps=steps, name="check_overview_after", action=service.check_data_overview)

    for step in steps:
        if step.get("status") == "warning" and step.get("message"):
            warnings.append(str(step["message"]))
        if step.get("name") == "update_twse_daily_prices":
            result = step.get("result")
            if isinstance(result, dict):
                warnings.extend(_twse_skip_warning_messages(result))
        if step.get("name") == "update_tpex_daily_prices":
            result = step.get("result")
            if isinstance(result, dict):
                warnings.extend(_tpex_warning_messages(result))
    warnings = list(dict.fromkeys(warnings))
    final_status = "failed" if failed is not None else "passed_with_warnings" if warnings else "passed"
    completed_at = scheduled_now()
    payload = {
        "task": "baldr-data-update-quick-daily",
        "status": final_status,
        "run_id": run_id,
        "started_at": run_now.isoformat(),
        "completed_at": completed_at.isoformat(),
        "process_id": os.getpid(),
        "checked_at": completed_at.isoformat(),
        "data_root": str(config.data_root),
        "output_root": str(config.output_root),
        "formal_output_root": str(formal_output_root),
        "authorized_technical_output_roots": [
            str(path) for path in authorized_technical_output_roots
        ],
        "candidate_db_path": str(candidate_db_path) if candidate_db_path else None,
        "capacity_lock_path": str(capacity_lock_path),
        "capacity_reservation_acquired": capacity_reservation is not None,
        "start_date": start_date,
        "end_date": end_date,
        "calendar_resolution": _serializable_calendar_records(calendar_records),
        "log_path": str(log_path),
        "steps": steps,
        "warnings": warnings,
        "errors": [] if failed is None else [failed.get("message", "scheduled quick data update failed")],
        "writes_market_data_db": True,
        "writes_evidence_db": False,
        "auto_trading": False,
        "auto_lifecycle_action": False,
        "history_path": str(history_path),
        "technical_process_pool_enabled": config.technical_process_pool_enabled,
        "technical_process_pool_workers": config.technical_process_pool_workers,
        "technical_process_pool_max_in_flight": config.technical_process_pool_max_in_flight,
        "technical_process_pool_max_retries": config.technical_process_pool_max_retries,
        "capacity_preflight": capacity_preflight,
        "optional_source_policy": {
            "skip_broker_branch": bool(args.skip_broker_branch),
        },
    }
    try:
        from data_module.recommendation_calibration_source_contract import (
            publish_technical_indicator_receipt,
        )

        payload["technical_publication_receipt"] = publish_technical_indicator_receipt(
            output_root=config.output_root,
            update_status=payload,
            source_db=config.db_file,
            authorized_output_roots=authorized_technical_output_roots,
        )
    except Exception as exc:  # noqa: BLE001
        # The source-contract receipt is a shadow/audit artifact.  A custody
        # failure must remain visible without changing the data-update result.
        payload["technical_publication_receipt"] = {
            "status": "blocked",
            "reason": f"technical_publication_receipt_failed:{type(exc).__name__}",
            "error": str(exc),
        }
    payload["history"] = _append_history_safely(history_path, payload)
    _write_json(status_path, payload)
    logging.info("Scheduled quick data update finished with status=%s", final_status)
    release_heavy_chain_reservation(capacity_reservation)
    return 1 if failed is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
