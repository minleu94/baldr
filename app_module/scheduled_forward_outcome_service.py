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
from app_module.evidence_progress_receipt_service import (
    persist_evidence_progress_receipt,
)
from app_module.forward_performance_service import _has_complete_cohort_identity
from app_module.forward_performance_service import (
    ForwardOutcomeSummary,
    ForwardPerformanceService,
)
from app_module.forward_outcome_context import build_official_maturity_calendar
from app_module.scheduled_writer_reservation import (
    ScheduledWriterReservationError,
    wait_for_scheduled_writer_reservation,
)
from data_module.ml_storage_capacity import release_heavy_chain_reservation


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
SCHEDULED_WRITER_RESERVATION_TIMEOUT_SECONDS = 10_500
FORWARD_OUTCOME_COMPLETION_RESERVE_SECONDS = 3_600


class ScheduledForwardOutcomeError(RuntimeError):
    """排程 outcome producer 的輸入或來源不符合安全契約。"""


class _ScheduledWriterAcquireGuardBlocked(RuntimeError):
    """Keep a locked-run guard receipt pending until its lease is released."""


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
    calendar_cache_path: str | Path | None = None,
    temporary_closure_path: str | Path | None = None,
) -> dict[str, Any]:
    """執行一次有界 outcome 更新並保存 machine-readable receipt。

    ``confirm=False`` 只建立 dry-run receipt；即使呼叫端提供 production DB，
    也不會寫入。production DB 寫入另外需要 ``allow_production_db_confirm``，
    讓正式 task 的寫入意圖在 wrapper 與 receipt 中都清楚可見。開啟
    ``require_cohort_identity`` 時，沒有明確策略／成本／benchmark／universe／horizon
    的事件會在計算前跳過並統計，不會佔用 outcome 寫入額度。
    """

    invocation_at = datetime.now(TAIPEI)
    natural_clock = now is None
    checked_raw = now or invocation_at
    checked_at = _require_aware_datetime(checked_raw).astimezone(TAIPEI)
    resolved_db = Path(db_path).expanduser().resolve() if db_path is not None else Path(config.db_file).expanduser().resolve()
    resolved_output = (
        Path(output_root).expanduser().resolve()
        if output_root is not None
        else Path(config.output_root).expanduser().resolve()
    )
    reservation_root = Path(config.output_root).expanduser().resolve()
    status_dir = resolved_output / "scheduled" / "forward_outcomes"
    status_path = status_dir / "latest_status.json"
    run_id = checked_at.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%S%fZ")
    run_path = status_dir / "runs" / f"{run_id}.json"

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "task": TASK_NAME,
        "run_id": run_id,
        "status": "running",
        "invocation_started_at": invocation_at.isoformat(timespec="seconds"),
        "checked_at": checked_at.isoformat(timespec="seconds"),
        "database_mode": "read_write_only_when_confirmed",
        "db_path": str(resolved_db),
        "output_root": str(resolved_output),
        "artifact_output_root": str(resolved_output),
        "canonical_reservation_root": str(reservation_root),
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

    reservation = None
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
        initial_preflight = _read_only_db_preflight(resolved_db)
        payload["source_preflight"] = initial_preflight
        payload["source_db_before"] = _file_stat(resolved_db)
        if not bool(initial_preflight.get("ready")):
            payload.update(
                {
                    "status": "blocked",
                    "blockers": list(initial_preflight.get("blockers") or []),
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

        if confirm:
            latest_acquire_at = datetime.combine(
                invocation_at.date() + timedelta(days=1),
                datetime.min.time(),
                tzinfo=TAIPEI,
            ) - timedelta(seconds=FORWARD_OUTCOME_COMPLETION_RESERVE_SECONDS)

            def publish_wait_progress(progress: Mapping[str, object]) -> None:
                status_path.parent.mkdir(parents=True, exist_ok=True)
                wait_status = {
                    "schema_version": SCHEMA_VERSION,
                    "task": TASK_NAME,
                    "run_id": run_id,
                    "status": "waiting_for_heavy_chain_reservation",
                    "invocation_started_at": invocation_at.isoformat(timespec="seconds"),
                    "db_path": str(resolved_db),
                    "output_root": str(resolved_output),
                    "artifact_output_root": str(resolved_output),
                    "canonical_reservation_root": str(reservation_root),
                    "confirm": True,
                    "writes_evidence_db": False,
                    "reservation_wait": dict(progress),
                }
                _write_atomic(
                    status_path,
                    json.dumps(wait_status, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                )

            try:
                wait_result = wait_for_scheduled_writer_reservation(
                    release_root=reservation_root / "release_v4",
                    timeout_seconds=SCHEDULED_WRITER_RESERVATION_TIMEOUT_SECONDS,
                    latest_acquire_at=latest_acquire_at,
                    on_progress=publish_wait_progress,
                )
            except ScheduledWriterReservationError as exc:
                payload.update(
                    {
                        "status": "blocked",
                        "reservation_wait": dict(exc.receipt),
                        "blockers": [
                            f"heavy_chain_reservation_failed:{type(exc.cause).__name__}"
                        ],
                        "exit_code": 2,
                        "writes_evidence_db": False,
                    }
                )
                raise _ScheduledWriterAcquireGuardBlocked
            if wait_result.reservation is None:
                payload.update(
                    {
                        "status": "blocked",
                        "reservation_wait": dict(wait_result.receipt),
                        "blockers": ["heavy_chain_reservation_timeout"],
                        "exit_code": 2,
                        "writes_evidence_db": False,
                    }
                )
                return _persist_receipt(payload, status_path=status_path, run_path=run_path)
            reservation = wait_result.reservation
            payload["reservation_wait"] = dict(wait_result.receipt)
            actual_after_acquire = datetime.now(TAIPEI)
            acquire_guard = {
                "checked_at": actual_after_acquire.isoformat(timespec="seconds"),
                "latest_acquire_at": latest_acquire_at.isoformat(timespec="seconds"),
                "completion_reserve_seconds": FORWARD_OUTCOME_COMPLETION_RESERVE_SECONDS,
                "passed": (
                    actual_after_acquire.date() == invocation_at.date()
                    and actual_after_acquire < latest_acquire_at
                ),
            }
            payload["reservation_acquire_guard"] = acquire_guard
            if not bool(acquire_guard["passed"]):
                checked_at = actual_after_acquire
                payload.update(
                    {
                        "checked_at": checked_at.isoformat(timespec="seconds"),
                        "status": "blocked",
                        "blockers": [
                            "heavy_chain_reservation_crossed_taipei_day"
                            if checked_at.date() != invocation_at.date()
                            else "heavy_chain_reservation_after_completion_cutoff"
                        ],
                        "exit_code": 2,
                        "writes_evidence_db": False,
                    }
                )
                raise _ScheduledWriterAcquireGuardBlocked
            if natural_clock:
                checked_at = actual_after_acquire
        else:
            payload["reservation_wait"] = {
                "status": "not_required",
                "reason": "dry_run_does_not_write_evidence_db",
            }

        # Natural checked_at and all default date bounds are chosen only after
        # the writer reservation is held. Explicit replay clocks remain exact.
        if natural_clock and reservation is not None:
            payload["checked_at"] = checked_at.isoformat(timespec="seconds")
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
        maturity_calendar = build_official_maturity_calendar(
            config=config,
            observed_at=checked_at,
            calendar_cache_path=calendar_cache_path,
            temporary_closure_path=temporary_closure_path,
        )
        payload["maturity_calendar"] = maturity_calendar.describe()
        payload["calendar_observation"] = _read_calendar_observation(
            resolved_output,
            checked_at.date(),
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
            if reservation is not None:
                raise _ScheduledWriterAcquireGuardBlocked
            return _persist_receipt(payload, status_path=status_path, run_path=run_path)

        repository = EvidenceEventRepository(
            config,
            db_path=resolved_db,
            read_only=not confirm,
        )
        service = ForwardPerformanceService(
            config,
            repository,
            db_path=resolved_db,
            maturity_calendar=maturity_calendar,
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
            invocation_at=checked_at,
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
            require_cohort_identity=require_cohort_identity,
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
        _apply_health_terminal_state(payload, confirm=confirm)
    except ScheduledWriterReservationError as exc:
        payload.update(
            {
                "status": "blocked",
                "reservation_wait": dict(exc.receipt),
                "blockers": [f"heavy_chain_reservation_failed:{type(exc.cause).__name__}"],
                "exit_code": 2,
                "writes_evidence_db": False,
            }
        )
    except _ScheduledWriterAcquireGuardBlocked:
        # Publish this terminal state only after finally releases the lease.
        pass
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
    finally:
        if reservation is not None:
            try:
                release_heavy_chain_reservation(reservation)
            except Exception as exc:  # noqa: BLE001 - lock release is part of writer custody
                payload.update(
                    {
                        "status": "blocked",
                        "exit_code": 2,
                        "reservation_release_error": f"{type(exc).__name__}:{exc}",
                        "blockers": _merge_text_items(
                            payload.get("blockers"),
                            "heavy_chain_reservation_release_failed",
                        ),
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


_HEALTH_BLOCKING_CLASSIFICATIONS = frozenset(
    {"actionable_engineering_blocker", "external_source_missing"}
)


def _apply_health_terminal_state(payload: dict[str, Any], *, confirm: bool) -> None:
    """Project bounded health onto the scheduled receipt terminal state.

    ``health`` was originally diagnostic-only, which allowed a confirmed run
    to report ``passed_with_warnings`` while its health already said that the
    event identity or source was not usable.  Natural maturity remains an
    explicit wait; source and engineering blockers fail closed.  The bounded
    outcome write remains idempotent, so a blocked receipt may still report
    rows written by that same run.
    """

    raw_health = payload.get("health")
    if not isinstance(raw_health, dict):
        return
    health = raw_health
    classification = str(health.get("classification") or "").strip()
    if not classification:
        return

    blockers = _text_items(health.get("blockers"))
    if classification in _HEALTH_BLOCKING_CLASSIFICATIONS and not blockers:
        blockers = [f"health:{classification}"]
    warnings = _text_items(health.get("warnings"))
    next_maturity_date = _optional_text(health.get("next_maturity_date"))
    blocking_reason = blockers[0] if blockers else None
    next_action = _health_next_action(classification, next_maturity_date)
    recovery_verification = _health_recovery_verification(
        classification=classification,
        next_maturity_date=next_maturity_date,
    )

    health.update(
        {
            "blocking_reason": blocking_reason,
            "next_action": next_action,
            "recovery_verification": recovery_verification,
        }
    )
    payload.update(
        {
            "health_classification": classification,
            "blocking_reason": blocking_reason,
            "next_action": next_action,
            "next_maturity_date": next_maturity_date,
            "recovery_verification": recovery_verification,
            "blockers": _merge_text_items(payload.get("blockers"), blockers),
            "warnings": _merge_text_items(payload.get("warnings"), warnings),
        }
    )

    # A dry-run remains a candidate receipt so callers can inspect the plan.
    # A confirmed run must not exit successfully when health says the source
    # or cohort is unusable.  This is deliberately after the bounded writer:
    # retrying the same natural key is safe and must not create duplicates.
    if confirm and classification in _HEALTH_BLOCKING_CLASSIFICATIONS:
        payload.update({"status": "blocked", "exit_code": 2})


def _health_next_action(classification: str, next_maturity_date: str | None) -> str:
    if classification == "actionable_engineering_blocker":
        return (
            "修正未來 producer/caller 的 cohort identity 或來源路徑；"
            "不回填既有事件，修正後從下一個自然日重跑 bounded producer。"
        )
    if classification == "external_source_missing":
        return (
            "補齊指定事件、價格或 benchmark 官方來源後重跑相同 bounded window；"
            "不補未來價格、不做 historical backfill。"
        )
    if classification == "waiting_for_natural_maturity":
        if next_maturity_date:
            return (
                f"等待官方交易日 {next_maturity_date} 的可見價格觀測；"
                "成熟前不回填、不補未來資料。"
            )
        return "等待下一個官方交易日的可見價格觀測；成熟前不回填、不補未來資料。"
    if classification == "normal_no_new_outcomes":
        return "下一個自然日以相同 bounded window 冪等重跑，不為製造數字改模型。"
    return "持續下一個自然日的 bounded 觀測；維持 research-only 與 no-lookahead 邊界。"


def _health_recovery_verification(
    *,
    classification: str,
    next_maturity_date: str | None,
) -> dict[str, Any]:
    if classification == "actionable_engineering_blocker":
        return {
            "status": "required",
            "expected_health_classifications": [
                "waiting_for_natural_maturity",
                "normal_completion",
                "normal_no_new_outcomes",
            ],
            "checks": [
                "events_skipped_incomplete_identity=0_for_current_bounded_selection",
                "source_preflight.ready=true",
                "historical_backfill=false",
                "outcome_natural_key_idempotent",
            ],
        }
    if classification == "external_source_missing":
        return {
            "status": "required",
            "expected_health_classifications": [
                "waiting_for_natural_maturity",
                "normal_completion",
                "normal_no_new_outcomes",
            ],
            "checks": [
                "source_preflight.ready=true",
                "missing_source_blockers_resolved",
                "no_future_dated_observations",
                "historical_backfill=false",
            ],
        }
    if classification == "waiting_for_natural_maturity":
        return {
            "status": "wait_until_natural_maturity",
            "expected_health_classifications": [
                "normal_completion",
                "normal_no_new_outcomes",
            ],
            "next_maturity_date": next_maturity_date,
            "checks": [
                "data_as_of_date_not_future",
                "outcome_status=ready_or_explicit_pending",
                "historical_backfill=false",
                "outcome_natural_key_idempotent",
            ],
        }
    return {
        "status": "not_required",
        "expected_health_classifications": [classification],
        "checks": [
            "health_blockers_empty",
            "bounded_window_preserved",
            "historical_backfill=false",
            "outcome_natural_key_idempotent",
        ],
    }


def _text_items(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        values = value
    elif value is None or isinstance(value, Mapping):
        values = ()
    else:
        values = (value,)
    result: list[str] = []
    for item in values:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def _merge_text_items(*values: object) -> list[str]:
    result: list[str] = []
    for value in values:
        for item in _text_items(value):
            if item not in result:
                result.append(item)
    return result


def _optional_text(value: object) -> str | None:
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return None
    text = str(value).strip()
    return text or None


def _has_explicit_v4_cohort_identity(event: Any) -> bool:
    metadata = event.metadata if isinstance(event.metadata, Mapping) else {}
    return all(
        str(metadata.get(key) or "").strip()
        for key in (
            "universe_policy_id",
            "universe_policy_hash",
            "universe_snapshot_id",
            "universe_snapshot_hash",
        )
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
    require_cohort_identity: bool,
) -> dict[str, Any]:
    """建立 bounded、可恢復的跨日證據健康摘要。

    這裡重用與 outcome producer 相同的「未完成 outcome 優先」順序，讓舊
    pending 長窗口不會被當日新事件長期排擠。健康摘要只讀取，不改寫 SQLite。
    """

    repository = EvidenceEventRepository(config, db_path=db_path, read_only=True)
    diagnostic_events = repository.list_events(
        event_type=event_type,
        symbol=symbol,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        limit=limit,
        incomplete_outcomes_first=True,
        outcome_windows=windows,
    )
    if require_cohort_identity:
        # Keep health aligned with the producer's second, identity-gated query.
        # The first query is retained only as a bounded diagnostic sample so a
        # large legacy backlog cannot make health disagree with the write plan.
        events = repository.list_events(
            event_type=event_type,
            symbol=symbol,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            limit=limit,
            incomplete_outcomes_first=True,
            outcome_windows=windows,
            complete_cohort_identity_only=True,
        )
        complete_events = [event for event in events if _has_complete_cohort_identity(event)]
        skipped = sum(
            not _has_complete_cohort_identity(event) for event in diagnostic_events
        )
    else:
        complete_events = [
            event for event in diagnostic_events if _has_complete_cohort_identity(event)
        ]
        skipped = len(diagnostic_events) - len(complete_events)
    horizon_counts: dict[str, dict[str, int]] = {
        str(window): {"ready": 0, "pending": 0, "missing": 0}
        for window in windows
    }
    cohorts: dict[str, dict[str, Any]] = {}
    pending_dates: list[str] = []
    calendar_metadata_count = 0
    calendar_waiting_count = 0
    planned_maturity_elapsed_count = 0
    calendar_mismatch_count = 0
    pending_date_bases: list[str] = []
    outcome_source_gaps: list[dict[str, Any]] = []
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
            else:
                metadata = outcome.metadata if isinstance(outcome.metadata, Mapping) else {}
                comparison = metadata.get("maturity_calendar_comparison")
                if "planned_official_calendar" in metadata:
                    calendar_metadata_count += 1
                if comparison == "blocked_mismatch":
                    calendar_mismatch_count += 1
                outcome_status = getattr(
                    outcome.outcome_status,
                    "value",
                    str(outcome.outcome_status),
                )
                target_price_state = metadata.get("target_price_state")
                source_price_gap_reason = metadata.get("source_price_gap_reason")
                if (
                    target_price_state == "missing_at_planned_official_session"
                    or (isinstance(source_price_gap_reason, str) and source_price_gap_reason)
                ):
                    lookup_detail = metadata.get("official_target_price_lookup_detail")
                    outcome_source_gaps.append(
                        {
                            "event_id": outcome.event_id,
                            "symbol": event.symbol,
                            "window_days": int(window),
                            "outcome_status": outcome_status,
                            "maturity_basis": metadata.get("maturity_basis"),
                            "planned_official_maturity_date": metadata.get(
                                "planned_official_maturity_date"
                            ),
                            "expected_maturity_date": metadata.get(
                                "expected_maturity_date"
                            ),
                            "target_price_state": target_price_state,
                            "source_price_gap_reason": source_price_gap_reason,
                            "official_target_price_lookup_detail": (
                                dict(lookup_detail)
                                if isinstance(lookup_detail, Mapping)
                                else lookup_detail
                            ),
                        }
                    )
                if outcome_status == "ready":
                    state = "ready"
                elif outcome_status in {"pending", "insufficient_future_data"}:
                    state = "pending"
                    planned = metadata.get("planned_official_maturity_date")
                    planned_status = metadata.get("planned_official_maturity_status")
                    if planned_status == "waiting_for_calendar":
                        calendar_waiting_count += 1
                    if planned:
                        planned_text = str(planned)[:10]
                        try:
                            planned_date = date.fromisoformat(planned_text)
                        except ValueError:
                            planned_date = None
                        if planned_date is not None and planned_date > checked_at.date():
                            pending_dates.append(planned_text)
                            calendar_payload = metadata.get(
                                "planned_official_calendar"
                            )
                            if isinstance(calendar_payload, Mapping):
                                pending_date_bases.append(
                                    str(
                                        calendar_payload.get("status")
                                        or "unknown"
                                    )
                                )
                        elif planned_date is not None:
                            planned_maturity_elapsed_count += 1
                else:
                    state = "missing"
            horizon_counts[str(window)][state] += 1
            cohort["horizons"][str(window)][state] += 1

    # Only an explicit V4 policy+snapshot identity can release the cut-over
    # blocker.  The compatibility path in ``_has_complete_cohort_identity``
    # still lets legacy ``universe_id`` rows be measured, but those rows are
    # not evidence that the new cohort producer is healthy.
    explicit_v4_events = [
        event for event in complete_events if _has_explicit_v4_cohort_identity(event)
    ]

    for item in cohorts.values():
        decision_dates = sorted(item.pop("decision_dates"))
        item["decision_dates"] = decision_dates
        item["decision_day_count"] = len(decision_dates)
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

    # A legacy backlog is expected during the V4 cohort cut-over.  It is
    # intentionally skipped and never backfilled, but it must not starve or
    # block a bounded run that already found at least one new complete cohort.
    # Keep the hard blocker for the true failure mode: the bounded selection
    # contains only incomplete identities and therefore has no safe event to
    # evaluate.
    if (summary.events_skipped_incomplete_identity or skipped) and not explicit_v4_events:
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

    if calendar_mismatch_count:
        blockers.append("maturity_calendar_comparison_blocked")
        classification = "actionable_engineering_blocker"
    if summary.blocked_time_contract_count:
        if "official_maturity_calendar_unavailable" not in blockers:
            blockers.append("official_maturity_calendar_unavailable")
        classification = "actionable_engineering_blocker"

    warning_values: list[str] = []
    if summary.pending_insufficient_future_data and not pending_dates:
        if calendar_waiting_count or calendar_metadata_count == 0:
            warning_values.append("no_maturity_calendar_observation")
        if planned_maturity_elapsed_count:
            warning_values.append("planned_maturity_elapsed_without_outcome_price")
    if calendar_mismatch_count:
        warning_values.append("maturity_calendar_comparison_blocked")
    if summary.blocked_time_contract_count:
        warning_values.append("official_maturity_calendar_unavailable")

    return {
        "schema_version": "scheduled-forward-outcome-health.v2",
        "classification": classification,
        "blocked_time_contract_count": int(summary.blocked_time_contract_count),
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
        "next_maturity_date_basis": (
            (
                "official_annual_plan_only"
                if pending_date_bases
                and all(item == "annual_plan_only" for item in pending_date_bases)
                else "verified_official_planned_calendar"
                if pending_dates
                else None
            )
        ),
        "planned_official_maturity": {
            "pending_future_count": len(pending_dates),
            "calendar_metadata_count": calendar_metadata_count,
            "waiting_for_calendar_count": calendar_waiting_count,
            "elapsed_without_outcome_price_count": planned_maturity_elapsed_count,
            "comparison_blocked_count": calendar_mismatch_count,
            "time_contract_blocked_count": int(summary.blocked_time_contract_count),
        },
        "outcome_source_gaps": sorted(
            outcome_source_gaps,
            key=lambda item: (
                str(item.get("planned_official_maturity_date") or ""),
                str(item.get("symbol") or ""),
                int(item.get("window_days") or 0),
                str(item.get("event_id") or ""),
            ),
        ),
        "outcome_source_gap_count": len(outcome_source_gaps),
        "blockers": blockers,
        "warnings": [
            *warning_values,
            *(
                [
                    "legacy_incomplete_identity_skipped_without_backfill"
                ]
                if (summary.events_skipped_incomplete_identity or skipped)
                and explicit_v4_events
                else []
            ),
        ],
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


def _read_calendar_observation(output_root: Path, target_date: date) -> dict[str, Any]:
    """Read the latest official-calendar observation without probing or writing."""

    if target_date.weekday() >= 5:
        return {
            "date": target_date.isoformat(),
            "is_trading_day": False,
            "reason_code": "weekend_closed",
            "source": "weekday_boundary",
        }

    status_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {
            "date": target_date.isoformat(),
            "is_trading_day": None,
            "reason_code": "official_calendar_observation_unavailable",
            "source_status_path": str(status_path),
        }
    if not isinstance(payload, dict):
        return {
            "date": target_date.isoformat(),
            "is_trading_day": None,
            "reason_code": "official_calendar_observation_invalid",
            "source_status_path": str(status_path),
        }
    checks = payload.get("checks")
    checks_mapping = checks if isinstance(checks, dict) else {}
    calendar = checks_mapping.get("official_calendar")
    calendar_mapping = calendar if isinstance(calendar, dict) else {}
    checked_at = str(payload.get("checked_at") or "").strip()
    if checked_at[:10] != target_date.isoformat():
        return {
            "date": target_date.isoformat(),
            "is_trading_day": None,
            "reason_code": "official_calendar_observation_stale",
            "source_status_path": str(status_path),
        }
    records = calendar_mapping.get("records")
    if calendar_mapping.get("freshness_status") == "current" and isinstance(records, list):
        for record in records:
            if not isinstance(record, dict):
                continue
            record_date = str(record.get("date_str") or "").strip()[:10]
            if record_date != target_date.isoformat():
                continue
            state = record.get("is_trading_day")
            return {
                "date": target_date.isoformat(),
                "is_trading_day": state if isinstance(state, bool) else None,
                "reason_code": str(
                    record.get("reason_code")
                    or "official_calendar_observation_invalid"
                ),
                "source": "data_freshness_official_calendar",
                "source_status_path": str(status_path),
            }
    return {
        "date": target_date.isoformat(),
        "is_trading_day": None,
        "reason_code": "official_calendar_observation_unknown",
        "source_status_path": str(status_path),
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
    try:
        progress = persist_evidence_progress_receipt(
            result,
            output_root=status_path.parent.parent.parent,
        )
        result["progress_receipt_path"] = progress["status_path"]
        result["progress_run_path"] = progress["run_path"]
        result["progress_receipt_idempotent"] = bool(progress["idempotent"])
    except (OSError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        result["status"] = "blocked"
        result["exit_code"] = 2
        result["blockers"] = _merge_text_items(
            result.get("blockers"),
            f"progress_receipt_write_failed:{type(exc).__name__}",
        )
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
