"""有界的每日 forward outcome producer。

這個 service 只負責把既有 Evidence event 的 close-to-close research outcome
寫回 ``evidence_outcomes``。它不建立事件、不改推薦、不改 Paper／Formal 狀態，
也不提供任何交易動作。排程入口必須明確使用 ``confirm``，並將查詢範圍限制在
當下可見日期與固定事件數上限內。
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.forward_performance_service import _has_complete_cohort_identity
from app_module.forward_performance_service import (
    ForwardOutcomeSummary,
    ForwardPerformanceService,
)


TASK_NAME = "baldr-forward-outcomes-daily"
SCHEMA_VERSION = "scheduled-forward-outcomes.v1"
RETURN_BASIS = "close_to_close_event_date"
DEFAULT_WINDOWS = (5, 10, 20, 60)
DEFAULT_LOOKBACK_CALENDAR_DAYS = 120
DEFAULT_MAX_EVENTS = 2500
MAX_LOOKBACK_CALENDAR_DAYS = 3660
MAX_EVENTS = 100_000
MAX_WINDOWS = 16
TAIPEI = ZoneInfo("Asia/Taipei")


class ScheduledForwardOutcomeError(RuntimeError):
    """排程 outcome producer 的輸入或來源不符合安全契約。"""


def run_scheduled_forward_outcomes(
    *,
    config: Any,
    db_path: str | Path | None = None,
    output_root: str | Path | None = None,
    now: datetime | None = None,
    confirm: bool = False,
    allow_production_db_confirm: bool = False,
    windows: Iterable[int] = DEFAULT_WINDOWS,
    lookback_calendar_days: int = DEFAULT_LOOKBACK_CALENDAR_DAYS,
    max_events: int = DEFAULT_MAX_EVENTS,
    start_date: str | None = None,
    end_date: str | None = None,
    data_as_of_date: str | None = None,
    event_type: str | None = None,
    symbol: str | None = None,
    require_cohort_identity: bool = False,
) -> dict[str, Any]:
    """執行一次有界 outcome 更新並保存 machine-readable receipt。

    ``confirm=False`` 只建立 dry-run receipt；即使呼叫端提供 production DB，
    也不會寫入。production DB 寫入另外需要 ``allow_production_db_confirm``，
    讓正式 task 的寫入意圖在 wrapper 與 receipt 中都清楚可見。開啟
    ``require_cohort_identity`` 時，沒有明確策略／成本／benchmark／universe／horizon
    的事件會在計算前跳過並統計，不會佔用 outcome 寫入額度。
    """

    checked_raw = now or datetime.now(TAIPEI)
    checked_at = _require_aware_datetime(checked_raw).astimezone(TAIPEI)
    resolved_db = Path(db_path).expanduser().resolve() if db_path is not None else Path(config.db_file).expanduser().resolve()
    resolved_output = (
        Path(output_root).expanduser().resolve()
        if output_root is not None
        else Path(config.output_root).expanduser().resolve()
    )
    status_dir = resolved_output / "scheduled" / "forward_outcomes"
    status_path = status_dir / "latest_status.json"
    run_id = checked_at.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%S%fZ")
    run_path = status_dir / "runs" / f"{run_id}.json"

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "task": TASK_NAME,
        "run_id": run_id,
        "status": "running",
        "checked_at": checked_at.isoformat(timespec="seconds"),
        "database_mode": "read_write_only_when_confirmed",
        "db_path": str(resolved_db),
        "output_root": str(resolved_output),
        "return_basis": RETURN_BASIS,
        "confirm": bool(confirm),
        "writes_evidence_db": False,
        "production_scheduler_allowed": False,
        "research_only": True,
        "auto_trading": False,
        "broker_order_allowed": False,
        "historical_backfill": False,
        "event_type": event_type,
        "symbol": symbol,
        "require_cohort_identity": bool(require_cohort_identity),
    }

    try:
        normalized_windows = _normalise_windows(windows)
        lookback = _positive_bounded_int(
            lookback_calendar_days,
            label="lookback_calendar_days",
            maximum=MAX_LOOKBACK_CALENDAR_DAYS,
        )
        bounded_max_events = _positive_bounded_int(
            max_events,
            label="max_events",
            maximum=MAX_EVENTS,
        )
        visible_date = _normalise_iso_date(data_as_of_date, label="data_as_of_date")
        if visible_date is None:
            visible_date = checked_at.date()
        if visible_date > checked_at.date():
            raise ScheduledForwardOutcomeError("data_as_of_date cannot be future-dated")
        resolved_start = _normalise_iso_date(start_date, label="start_date")
        if resolved_start is None:
            resolved_start = visible_date - timedelta(days=lookback)
        resolved_end = _normalise_iso_date(end_date, label="end_date")
        if resolved_end is None:
            resolved_end = visible_date
        if resolved_start > resolved_end:
            raise ScheduledForwardOutcomeError("start_date must not be after end_date")
        if resolved_end > visible_date:
            raise ScheduledForwardOutcomeError("end_date cannot be later than data_as_of_date")

        payload.update(
            {
                "windows": list(normalized_windows),
                "lookback_calendar_days": lookback,
                "max_events": bounded_max_events,
                "start_date": resolved_start.isoformat(),
                "end_date": resolved_end.isoformat(),
                "data_as_of_date": visible_date.isoformat(),
            }
        )

        preflight = _read_only_db_preflight(resolved_db)
        payload["source_preflight"] = preflight
        before = _file_stat(resolved_db)
        payload["source_db_before"] = before
        if not bool(preflight.get("ready")):
            payload.update(
                {
                    "status": "blocked",
                    "blockers": list(preflight.get("blockers") or []),
                    "exit_code": 2,
                }
            )
            return _persist_receipt(payload, status_path=status_path, run_path=run_path)

        production_db = Path(config.db_file).expanduser().resolve()
        if confirm and resolved_db == production_db and not allow_production_db_confirm:
            payload.update(
                {
                    "status": "blocked",
                    "blockers": ["production_db_confirmation_required"],
                    "exit_code": 2,
                }
            )
            return _persist_receipt(payload, status_path=status_path, run_path=run_path)

        repository = EvidenceEventRepository(config, db_path=resolved_db)
        service = ForwardPerformanceService(
            config,
            repository,
            db_path=resolved_db,
        )
        summary = service.calculate(
            windows=normalized_windows,
            dry_run=not confirm,
            start_date=resolved_start.isoformat(),
            end_date=resolved_end.isoformat(),
            event_type=event_type,
            symbol=symbol,
            limit=bounded_max_events,
            data_as_of_date=visible_date.isoformat(),
            require_cohort_identity=require_cohort_identity,
        )
        summary_payload = asdict(summary)
        summary_payload["outcomes_written"] = (
            summary.outcomes_created + summary.outcomes_updated
        )
        payload["summary"] = summary_payload
        payload["health"] = _build_daily_health(
            config=config,
            db_path=resolved_db,
            start_date=resolved_start,
            end_date=resolved_end,
            event_type=event_type,
            symbol=symbol,
            limit=bounded_max_events,
            windows=normalized_windows,
            checked_at=checked_at,
            summary=summary,
        )
        payload["writes_evidence_db"] = bool(confirm)
        payload["source_db_after"] = _file_stat(resolved_db)
        payload["source_db_changed"] = payload["source_db_before"] != payload["source_db_after"]
        if not confirm:
            status = "dry_run"
            exit_code = 0
        elif summary.events_scanned == 0:
            status = "degraded"
            exit_code = 0
            payload["warnings"] = ["no_events_in_window"]
        elif _summary_has_warnings(summary):
            status = "passed_with_warnings"
            exit_code = 0
        else:
            status = "passed"
            exit_code = 0
        payload.update({"status": status, "exit_code": exit_code})
    except (ScheduledForwardOutcomeError, ValueError, OSError, sqlite3.Error) as exc:
        payload.update(
            {
                "status": "blocked",
                "blockers": [f"producer_error:{type(exc).__name__}:{str(exc)}"],
                "exit_code": 2,
            }
        )
    except Exception as exc:  # noqa: BLE001 - scheduled boundary must fail closed
        payload.update(
            {
                "status": "blocked",
                "blockers": [f"producer_unexpected_error:{type(exc).__name__}"],
                "exit_code": 2,
            }
        )
    return _persist_receipt(payload, status_path=status_path, run_path=run_path)


def _summary_has_warnings(summary: ForwardOutcomeSummary) -> bool:
    return bool(
        summary.warnings_count
        or summary.pending_insufficient_future_data
        or summary.missing_event_price
        or summary.missing_outcome_price
        or summary.missing_benchmark
        or summary.missing_industry_benchmark
        or summary.events_skipped_incomplete_identity
    )


def _build_daily_health(
    *,
    config: Any,
    db_path: Path,
    start_date: date,
    end_date: date,
    event_type: str | None,
    symbol: str | None,
    limit: int,
    windows: tuple[int, ...],
    checked_at: datetime,
    summary: ForwardOutcomeSummary,
) -> dict[str, Any]:
    """建立 bounded、可恢復的跨日證據健康摘要。

    這裡重用與 outcome producer 相同的「未完成 outcome 優先」順序，讓舊
    pending 長窗口不會被當日新事件長期排擠。健康摘要只讀取，不改寫 SQLite。
    """

    repository = EvidenceEventRepository(config, db_path=db_path)
    events = repository.list_events(
        event_type=event_type,
        symbol=symbol,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        limit=limit,
        incomplete_outcomes_first=True,
        outcome_windows=windows,
    )
    complete_events = [event for event in events if _has_complete_cohort_identity(event)]
    skipped = len(events) - len(complete_events)
    horizon_counts: dict[str, dict[str, int]] = {
        str(window): {"ready": 0, "pending": 0, "missing": 0}
        for window in windows
    }
    cohorts: dict[str, dict[str, Any]] = {}
    pending_dates: list[str] = []
    for event in complete_events:
        metadata = event.metadata if isinstance(event.metadata, Mapping) else {}
        policy_id = str(metadata.get("universe_policy_id") or metadata.get("universe_id") or "").strip()
        policy_hash = str(metadata.get("universe_policy_hash") or metadata.get("universe_hash") or "").strip()
        strategy_config_id = str(
            metadata.get("strategy_config_id")
            or metadata.get("strategy_config_hash")
            or "legacy-strategy-config"
        ).strip()
        tier = str(metadata.get("evidence_tier") or "unclassified").strip()
        cohort_id = ":".join(
            (
                str(event.strategy_version_id),
                strategy_config_id,
                policy_id,
                policy_hash or "legacy-universe-hash",
                str(event.cost_model_id),
                str(event.benchmark_id or ""),
                tier,
            )
        )
        cohort = cohorts.setdefault(
            cohort_id,
            {
                "cohort_id": cohort_id,
                "decision_dates": set(),
                "universe_snapshot_ids": set(),
                "horizons": {
                    str(window): {"ready": 0, "pending": 0, "missing": 0}
                    for window in windows
                },
            },
        )
        cohort["decision_dates"].add(str(event.decision_date))
        snapshot_id = str(metadata.get("universe_snapshot_id") or "").strip()
        if snapshot_id:
            cohort["universe_snapshot_ids"].add(snapshot_id)
        for window in windows:
            outcome = repository.get_outcome(event.event_id, window)
            if outcome is None:
                state = "missing"
            elif getattr(outcome.outcome_status, "value", str(outcome.outcome_status)) == "ready":
                state = "ready"
            elif getattr(outcome.outcome_status, "value", str(outcome.outcome_status)) in {
                "pending",
                "insufficient_future_data",
            }:
                state = "pending"
                expected = outcome.metadata.get("expected_maturity_date") if isinstance(outcome.metadata, Mapping) else None
                if expected:
                    pending_dates.append(str(expected)[:10])
            else:
                state = "missing"
            horizon_counts[str(window)][state] += 1
            cohort["horizons"][str(window)][state] += 1

    for item in cohorts.values():
        item["decision_day_count"] = len(item.pop("decision_dates"))
        item["universe_snapshot_ids"] = sorted(item["universe_snapshot_ids"])
        item["universe_snapshot_count"] = len(item["universe_snapshot_ids"])
    ordered_cohorts = [cohorts[key] for key in sorted(cohorts)]

    latest_capture_at = max(
        (str(event.created_at).strip() for event in complete_events if str(event.created_at).strip()),
        default=None,
    )
    latest_outcome_updated_at: str | None = None
    try:
        with sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            conn.execute("PRAGMA query_only = ON")
            row = conn.execute("SELECT MAX(calculated_at) FROM evidence_outcomes").fetchone()
            latest_outcome_updated_at = str(row[0]) if row and row[0] else None
    except sqlite3.Error:
        latest_outcome_updated_at = None

    if summary.events_skipped_incomplete_identity or skipped:
        classification = "actionable_engineering_blocker"
        blockers = ["events_missing_complete_cohort_identity"]
    elif summary.events_scanned == 0:
        classification = "external_source_missing"
        blockers = ["no_events_in_window"]
    elif (
        summary.missing_event_price
        or summary.missing_outcome_price
        or summary.missing_benchmark
        or summary.missing_industry_benchmark
    ):
        classification = "external_source_missing"
        blockers = []
        if summary.missing_event_price:
            blockers.append("event_price_missing")
        if summary.missing_outcome_price:
            blockers.append("outcome_price_missing")
        if summary.missing_benchmark:
            blockers.append("benchmark_missing")
        if summary.missing_industry_benchmark:
            blockers.append("industry_benchmark_missing")
    elif summary.pending_insufficient_future_data:
        classification = "waiting_for_natural_maturity"
        blockers = []
    elif summary.outcomes_created or summary.outcomes_updated:
        classification = "normal_completion"
        blockers = []
    else:
        classification = "normal_no_new_outcomes"
        blockers = []

    return {
        "schema_version": "scheduled-forward-outcome-health.v1",
        "classification": classification,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "bounded_limit": int(limit),
        "selection_order": "incomplete_outcomes_first_then_decision_date",
        "latest_qualifying_event_date": max(
            (str(event.decision_date) for event in complete_events),
            default=None,
        ),
        "qualifying_event_count": len(complete_events),
        "events_skipped_incomplete_identity": int(max(summary.events_skipped_incomplete_identity, skipped)),
        "cohort_count": len(ordered_cohorts),
        "cohorts": ordered_cohorts,
        "horizons": horizon_counts,
        "latest_capture_at": latest_capture_at,
        "latest_outcome_updated_at": latest_outcome_updated_at,
        "last_evaluation_at": checked_at.isoformat(timespec="seconds"),
        "next_maturity_date": min(pending_dates) if pending_dates else None,
        "blockers": blockers,
        "warnings": (
            ["no_maturity_calendar_observation"]
            if summary.pending_insufficient_future_data and not pending_dates
            else []
        ),
        "idempotency": {
            "natural_key": "(event_id, window_days, return_basis)",
            "duplicate_outcomes_created": 0,
            "outcomes_updated_on_retry": int(summary.outcomes_updated),
        },
    }


def _read_only_db_preflight(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "ready": False,
            "blockers": ["evidence_db_missing"],
            "tables": [],
            "read_only": True,
            "query_only": True,
        }
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            conn.execute("PRAGMA query_only = ON")
            conn.execute("PRAGMA busy_timeout = 30000")
            tables = tuple(
                sorted(
                    str(row[0])
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                )
            )
    except sqlite3.Error as exc:
        return {
            "ready": False,
            "blockers": [f"evidence_db_unavailable:{type(exc).__name__}"],
            "tables": [],
            "read_only": True,
            "query_only": True,
        }
    required = {"evidence_events", "evidence_outcomes", "daily_prices"}
    missing = tuple(sorted(required.difference(tables)))
    return {
        "ready": not missing,
        "blockers": [f"required_table_missing:{name}" for name in missing],
        "tables": list(tables),
        "required_tables": sorted(required),
        "read_only": True,
        "query_only": True,
    }


def _normalise_windows(values: Iterable[int]) -> tuple[int, ...]:
    parsed: set[int] = set()
    for raw in values:
        if isinstance(raw, bool):
            raise ScheduledForwardOutcomeError("windows must contain positive integers")
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ScheduledForwardOutcomeError("windows must contain positive integers") from exc
        if value <= 0:
            raise ScheduledForwardOutcomeError("windows must contain positive integers")
        parsed.add(value)
    if not parsed:
        raise ScheduledForwardOutcomeError("windows must include at least one integer")
    if len(parsed) > MAX_WINDOWS:
        raise ScheduledForwardOutcomeError(f"windows cannot exceed {MAX_WINDOWS} values")
    return tuple(sorted(parsed))


def _positive_bounded_int(value: int, *, label: str, maximum: int) -> int:
    if isinstance(value, bool):
        raise ScheduledForwardOutcomeError(f"{label} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ScheduledForwardOutcomeError(f"{label} must be a positive integer") from exc
    if parsed <= 0 or parsed > maximum:
        raise ScheduledForwardOutcomeError(f"{label} must be between 1 and {maximum}")
    return parsed


def _normalise_iso_date(value: str | None, *, label: str) -> date | None:
    if value is None or not str(value).strip():
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ScheduledForwardOutcomeError(f"{label} must use YYYY-MM-DD") from exc


def _require_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ScheduledForwardOutcomeError("now must include a timezone")
    return value


def _file_stat(path: Path) -> dict[str, int] | None:
    try:
        stat_result = path.stat()
    except OSError:
        return None
    return {"size_bytes": int(stat_result.st_size), "mtime_ns": int(stat_result.st_mtime_ns)}


def _persist_receipt(
    payload: Mapping[str, Any],
    *,
    status_path: Path,
    run_path: Path,
) -> dict[str, Any]:
    result = dict(payload)
    result.setdefault("blockers", [])
    result.setdefault("exit_code", 2 if result.get("status") == "blocked" else 0)
    result["status_path"] = str(status_path)
    result["run_path"] = str(run_path)
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try:
        run_path.parent.mkdir(parents=True, exist_ok=True)
        _write_create_only(run_path, encoded)
        status_path.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(status_path, encoded)
    except OSError as exc:
        # Receipt failure itself is a failed scheduled run.  Return a useful
        # object to the caller even when the output root is temporarily ACL
        # protected; never claim a successful persistent status in that case.
        result["status"] = "blocked"
        result["exit_code"] = 2
        result["blockers"] = [f"receipt_write_failed:{type(exc).__name__}"]
    return result


def _write_create_only(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
        stream.flush()


def _write_atomic(path: Path, text: str) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with open(fd, "w", encoding="utf-8", newline="\n", closefd=True) as stream:
            stream.write(text)
            stream.flush()
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


__all__ = [
    "DEFAULT_LOOKBACK_CALENDAR_DAYS",
    "DEFAULT_MAX_EVENTS",
    "DEFAULT_WINDOWS",
    "RETURN_BASIS",
    "SCHEMA_VERSION",
    "ScheduledForwardOutcomeError",
    "TASK_NAME",
    "run_scheduled_forward_outcomes",
]
