"""Bounded same-day dependency barrier for the current-observed G6 lane.

The mutable ``latest_status.json`` is used only to discover one raw run. Once a
same-day run id is observed, the barrier never follows a later pointer. The
returned immutable terminal pin is passed to the learning consumer, which
revalidates the full source/model lineage before use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from app_module.recommendation.queries import _read_regular_file_no_follow
from data_module.ml_research_output_boundary import (
    get_ml_research_root,
    resolve_ml_research_output_path,
)
from data_module.current_observed_capacity_eligibility import (
    classify_current_observed_raw_status,
    current_stock_research_capacity_passed,
)
from data_module.official_trading_calendar import OfficialTradingCalendar
from data_module.market_session_policy import resolve_project_market_session_boundary


TAIPEI = ZoneInfo("Asia/Taipei")
_RAW_STATUS_SCHEMA = "ml-raw-pit-refresh-status.v1"
_CYCLE_TERMINAL_SCHEMA = "current-stock-research-cycle-terminal.v1"
_MAX_STATUS_BYTES = 8 * 1024 * 1024
_MAX_TERMINAL_BYTES = 8 * 1024 * 1024
_DEFAULT_CALENDAR_ROOT = (
    Path(__file__).resolve().parents[2]
    / "output"
    / "paper_execution_eod_replay"
    / "calendar_cache"
)


@dataclass(frozen=True)
class CurrentObservedRawCyclePin:
    """Exact same-day raw run and immutable current-stock-cycle terminal."""

    raw_run_id: str
    source_date: str
    terminal_path: str
    terminal_sha256: str
    status_path: str
    status_sha256: str
    raw_status: str
    cycle_status: str
    wait_started_at: str
    wait_completed_at: str
    wait_deadline_at: str
    wait_seconds: float

    def learning_arguments(self, *, source_output_root: Path) -> list[str]:
        return [
            "--current-observed-source-output-root",
            str(source_output_root),
            "--current-observed-expected-raw-run-id",
            self.raw_run_id,
            "--current-observed-expected-cycle-terminal",
            self.terminal_path,
            "--current-observed-expected-cycle-terminal-sha256",
            self.terminal_sha256,
        ]

    def as_step(self) -> dict[str, Any]:
        return {
            "status": "completed",
            "raw_run_id": self.raw_run_id,
            "source_date": self.source_date,
            "terminal_receipt_path": self.terminal_path,
            "terminal_receipt_sha256": self.terminal_sha256,
            "raw_status_path": self.status_path,
            "raw_status_sha256": self.status_sha256,
            "raw_status": self.raw_status,
            "cycle_status": self.cycle_status,
            "wait_started_at": self.wait_started_at,
            "wait_completed_at": self.wait_completed_at,
            "wait_deadline_at": self.wait_deadline_at,
            "wait_seconds": self.wait_seconds,
            "next_action": "run_learning_with_exact_g6_terminal_pins",
        }


@dataclass(frozen=True)
class CurrentObservedRawCycleBlocked:
    """Fail-closed wait result with a typed reason and observed run identity."""

    reason: str
    wait_started_at: str
    wait_completed_at: str
    wait_deadline_at: str
    wait_seconds: float
    expected_source_date: str
    pinned_raw_run_id: str | None = None
    observed_status: str | None = None
    status_path: str | None = None
    status_sha256: str | None = None

    def as_step(self) -> dict[str, Any]:
        return {
            "status": "blocked",
            "reason": self.reason,
            "expected_source_date": self.expected_source_date,
            "pinned_raw_run_id": self.pinned_raw_run_id,
            "observed_status": self.observed_status,
            "raw_status_path": self.status_path,
            "raw_status_sha256": self.status_sha256,
            "wait_started_at": self.wait_started_at,
            "wait_completed_at": self.wait_completed_at,
            "wait_deadline_at": self.wait_deadline_at,
            "wait_seconds": self.wait_seconds,
            "next_action": "retain_blocker_and_retry_on_a_new_scheduled_run",
        }


def _parse_aware_datetime(value: object) -> datetime | None:
    if type(value) is not str or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _sha256_text(value: object) -> bool:
    if type(value) is not str:
        return False
    candidate = value.removeprefix("sha256:")
    return re.fullmatch(r"[0-9a-f]{64}", candidate) is not None


def _raw_status_eligible(payload: Mapping[str, Any]) -> bool:
    """Mirror the consumer's narrow raw terminal allowlist."""

    return classify_current_observed_raw_status(payload) != "ineligible"


def expected_current_observed_source_date(
    *,
    decision_date: date,
    observed_at: datetime,
    source_db: Path,
    calendar_cache_path: Path | None = None,
    temporary_closure_path: Path | None = None,
) -> str:
    """Resolve the raw cycle's latest session under the shared daily cutoff.

    The raw producer may publish the decision date itself after the project's
    04:30 America/Los_Angeles cutoff. The learning feature ``as_of`` date is a
    separate T-1 contract and must not be used to identify the G6 raw cycle.
    Exchange closures are resolved only through the verified offline calendar.
    """

    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("current-observed source date clock must be timezone-aware")
    if observed_at.astimezone(TAIPEI).date() != decision_date:
        raise ValueError("current-observed source date clock differs from Taipei decision date")
    boundary = resolve_project_market_session_boundary(observed_at)

    configured_calendar = calendar_cache_path
    if configured_calendar is None:
        configured = os.environ.get("NATURAL_MATURITY_CALENDAR_CACHE_PATH") or os.environ.get(
            "ML_FORWARD_CALENDAR_CACHE_ROOT"
        )
        configured_calendar = (
            Path(configured).expanduser().resolve()
            if configured and configured.strip()
            else _DEFAULT_CALENDAR_ROOT.resolve()
        )
    configured_closures = temporary_closure_path
    if configured_closures is None:
        configured = os.environ.get("NATURAL_MATURITY_TEMPORARY_CLOSURE_PATH")
        configured_closures = (
            Path(configured).expanduser().resolve()
            if configured and configured.strip()
            else None
        )

    calendar = OfficialTradingCalendar(
        db_path=source_db,
        calendar_cache_path=configured_calendar,
        temporary_closure_path=configured_closures,
    )
    latest_session = calendar.get_recent_official_trading_days(
        boundary.calendar_end_date,
        1,
        include_reference=True,
        allow_online_probe=False,
    )[-1]
    return str(latest_session["date_str"])


def wait_for_current_observed_raw_cycle(
    *,
    source_output_root: Path,
    research_root: Path,
    repository_root: Path | None = None,
    decision_date: date,
    expected_source_date: str,
    deadline_monotonic: float,
    max_wait_seconds: float,
    poll_seconds: float = 15.0,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    now_provider: Callable[[], datetime] | None = None,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> CurrentObservedRawCyclePin | CurrentObservedRawCycleBlocked:
    """Wait for exactly one same-day raw run and its verified immutable cycle.

    A run id is pinned as soon as a valid same-day raw status appears. Any later
    pointer change blocks immediately; the barrier never follows a newer run.
    The wait is bounded by both the caller's pipeline deadline and its own cap.
    """

    if not math.isfinite(max_wait_seconds) or not math.isfinite(poll_seconds):
        raise ValueError("current-observed wait limits must be finite")
    if not math.isfinite(deadline_monotonic):
        raise ValueError("current-observed pipeline deadline must be finite")
    if poll_seconds <= 0:
        raise ValueError("current-observed poll interval must be positive")
    started_mono = monotonic()
    deadline = min(deadline_monotonic, started_mono + max(0.0, max_wait_seconds))
    clock = now_provider or (lambda: datetime.now(TAIPEI))
    started_clock = clock()
    if started_clock.tzinfo is None or started_clock.utcoffset() is None:
        raise ValueError("current-observed wait clock must be timezone-aware")
    started_text = started_clock.isoformat(timespec="seconds")
    deadline_clock = started_clock.astimezone(timezone.utc) + timedelta(
        seconds=max(0.0, deadline - started_mono)
    )
    deadline_text = deadline_clock.astimezone(TAIPEI).isoformat(timespec="seconds")
    output_root = source_output_root.expanduser().resolve()
    repository = Path(repository_root or Path(__file__).resolve().parents[2]).expanduser().resolve()
    active_research_root = get_ml_research_root(repository_root=repository)
    legacy_research_root = resolve_ml_research_output_path(
        repository / "output" / "ml_research",
        repository_root=repository,
        access="read",
    )
    requested_research_root = resolve_ml_research_output_path(
        research_root.expanduser(),
        repository_root=repository,
        access="read",
    )
    if requested_research_root not in {active_research_root, legacy_research_root}:
        raise ValueError("research_root must be the active or legacy ML research root")
    accepted_research_roots = tuple(dict.fromkeys((active_research_root, legacy_research_root)))
    status_path = output_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json"
    pinned_run_id: str | None = None
    last_status: str | None = None
    last_status_sha256: str | None = None
    last_reason = "current_day_raw_run_not_yet_observed"

    def blocked(reason: str) -> CurrentObservedRawCycleBlocked:
        completed_clock = clock()
        if completed_clock.tzinfo is None or completed_clock.utcoffset() is None:
            raise ValueError("current-observed wait clock must be timezone-aware")
        return CurrentObservedRawCycleBlocked(
            reason=reason,
            wait_started_at=started_text,
            wait_completed_at=completed_clock.isoformat(timespec="seconds"),
            wait_deadline_at=deadline_text,
            wait_seconds=max(0.0, monotonic() - started_mono),
            expected_source_date=expected_source_date,
            pinned_raw_run_id=pinned_run_id,
            observed_status=last_status,
            status_path=str(status_path),
            status_sha256=last_status_sha256,
        )

    if max_wait_seconds <= 0 or deadline <= started_mono:
        return blocked("current_stock_cycle_wait_budget_exhausted_before_start")
    if started_clock.astimezone(TAIPEI).date() != decision_date:
        return blocked("current_stock_cycle_wait_started_after_decision_date")

    while monotonic() < deadline:
        now = clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("current-observed wait clock must be timezone-aware")
        if now.astimezone(TAIPEI).date() != decision_date:
            return blocked("current_stock_cycle_wait_crossed_decision_date")

        try:
            raw_bytes = _read_regular_file_no_follow(
                status_path,
                output_root,
                max_bytes=_MAX_STATUS_BYTES,
            )
            raw_payload = json.loads(raw_bytes.decode("utf-8"))
        except (OSError, RuntimeError, UnicodeError, json.JSONDecodeError, ValueError):
            raw_payload = None
            last_reason = "canonical_raw_status_missing_or_unreadable"
            last_status_sha256 = None

        if isinstance(raw_payload, Mapping):
            last_status_sha256 = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
            if raw_payload.get("schema_version") != _RAW_STATUS_SCHEMA:
                return blocked("canonical_raw_status_schema_mismatch")
            try:
                reported_root = Path(str(raw_payload.get("output_root") or "")).expanduser().resolve()
            except (OSError, RuntimeError, TypeError, ValueError):
                return blocked("canonical_raw_status_root_invalid")
            if reported_root != output_root:
                return blocked("canonical_raw_status_root_mismatch")
            run_id_value = raw_payload.get("run_id")
            started_at = _parse_aware_datetime(raw_payload.get("started_at"))
            if type(run_id_value) is not str or not run_id_value.strip() or started_at is None:
                last_reason = "canonical_raw_status_run_identity_incomplete"
            elif started_at.astimezone(TAIPEI).date() != decision_date:
                if pinned_run_id is not None:
                    return blocked("canonical_raw_status_start_date_changed_after_pin")
                last_reason = "current_day_raw_run_not_yet_observed"
            else:
                run_id = run_id_value.strip()
                if pinned_run_id is None:
                    pinned_run_id = run_id
                elif run_id != pinned_run_id:
                    return blocked("canonical_raw_status_pointer_changed_after_run_pin")

                last_status = str(raw_payload.get("status") or "")
                latest_core_date = raw_payload.get("latest_core_date")
                top_source_date = raw_payload.get("source_date")
                if latest_core_date not in (None, expected_source_date):
                    return blocked("raw_run_latest_core_date_differs_from_expected_session")
                if top_source_date not in (None, expected_source_date):
                    return blocked("raw_run_source_date_differs_from_expected_session")

                if last_status == "running":
                    last_reason = "pinned_raw_run_still_running"
                elif not _raw_status_eligible(raw_payload):
                    return blocked("pinned_raw_run_terminal_status_not_eligible")
                else:
                    if latest_core_date != expected_source_date:
                        return blocked("eligible_raw_run_missing_expected_latest_core_date")
                    child = raw_payload.get("current_stock_research_cycle")
                    if not isinstance(child, Mapping):
                        return blocked("pinned_raw_run_has_no_current_stock_cycle")
                    cycle_status = child.get("status")
                    child_source_date = child.get("source_date")
                    child_raw_run_id = child.get("raw_run_id")
                    if (
                        cycle_status not in {"completed", "skipped_same_inputs"}
                        or child_raw_run_id != run_id
                        or child_source_date != expected_source_date
                        or top_source_date not in (None, expected_source_date)
                    ):
                        return blocked("pinned_raw_run_cycle_is_not_same_run_date_success")
                    terminal_value = child.get("terminal_receipt_path")
                    terminal_sha = child.get("terminal_receipt_sha256")
                    if type(terminal_value) is not str or not terminal_value.strip() or not _sha256_text(terminal_sha):
                        return blocked("pinned_raw_run_cycle_terminal_pin_invalid")
                    terminal_candidate = Path(terminal_value).expanduser()
                    if not terminal_candidate.is_absolute():
                        return blocked("pinned_raw_run_cycle_terminal_path_not_absolute")
                    try:
                        terminal_path = resolve_ml_research_output_path(
                            terminal_candidate,
                            repository_root=repository,
                            access="read",
                        ).resolve(strict=True)
                        terminal_root = next(
                            root
                            for root in accepted_research_roots
                            if terminal_path.is_relative_to(root)
                        )
                        terminal_bytes = _read_regular_file_no_follow(
                            terminal_path,
                            terminal_root,
                            max_bytes=_MAX_TERMINAL_BYTES,
                        )
                    except (OSError, RuntimeError, TypeError, ValueError):
                        return blocked("pinned_raw_run_cycle_terminal_unreadable_or_outside_research_root")
                    actual_terminal_sha = "sha256:" + hashlib.sha256(terminal_bytes).hexdigest()
                    if actual_terminal_sha != terminal_sha:
                        return blocked("pinned_raw_run_cycle_terminal_sha256_mismatch")
                    try:
                        terminal_payload = json.loads(terminal_bytes.decode("utf-8"))
                    except (UnicodeError, json.JSONDecodeError):
                        return blocked("pinned_raw_run_cycle_terminal_json_invalid")
                    if (
                        not isinstance(terminal_payload, Mapping)
                        or terminal_payload.get("schema_version") != _CYCLE_TERMINAL_SCHEMA
                        or terminal_payload.get("status") != cycle_status
                        or terminal_payload.get("raw_run_id") != run_id
                        or terminal_payload.get("cycle_id") != run_id
                        or terminal_payload.get("source_date") != expected_source_date
                    ):
                        return blocked("pinned_raw_run_cycle_terminal_identity_mismatch")
                    if classify_current_observed_raw_status(raw_payload) == "blocked_insufficient_storage":
                        formal_output_root = raw_payload.get("output_root")
                        if type(formal_output_root) is not str or not formal_output_root.strip():
                            return blocked("formal_capacity_block_output_root_missing")
                        if cycle_status == "completed":
                            if not current_stock_research_capacity_passed(
                                terminal_payload,
                                expected_raw_run_id=run_id,
                                expected_source_date=expected_source_date,
                                formal_output_root=formal_output_root,
                                expected_research_root=terminal_root,
                            ):
                                return blocked("formal_capacity_block_g6_terminal_capacity_unverified")
                        elif cycle_status == "skipped_same_inputs":
                            try:
                                from ml_module.recommendation_calibration_evidence import (
                                    verify_current_observed_cycle_reuse,
                                )

                                reuse_identity = verify_current_observed_cycle_reuse(
                                    reuse_terminal_path=str(terminal_path),
                                    reuse_terminal_sha256=actual_terminal_sha,
                                    expected_raw_run_id=run_id,
                                    expected_source_date=expected_source_date,
                                    require_original_capacity=True,
                                    formal_output_root=formal_output_root,
                                )
                            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                                return blocked(
                                    "formal_capacity_block_g6_reuse_or_original_capacity_unverified"
                                )
                            if reuse_identity.get("original_capacity_verified") is not True:
                                return blocked(
                                    "formal_capacity_block_g6_reuse_capacity_proof_missing"
                                )
                    completed_clock = clock()
                    if (
                        completed_clock.tzinfo is None
                        or completed_clock.utcoffset() is None
                        or completed_clock.astimezone(TAIPEI).date() != decision_date
                    ):
                        return blocked("current_stock_cycle_wait_crossed_decision_date")
                    return CurrentObservedRawCyclePin(
                        raw_run_id=run_id,
                        source_date=expected_source_date,
                        terminal_path=str(terminal_path),
                        terminal_sha256=actual_terminal_sha,
                        status_path=str(status_path),
                        status_sha256=last_status_sha256,
                        raw_status=last_status,
                        cycle_status=str(cycle_status),
                        wait_started_at=started_text,
                        wait_completed_at=completed_clock.isoformat(timespec="seconds"),
                        wait_deadline_at=deadline_text,
                        wait_seconds=max(0.0, monotonic() - started_mono),
                    )

        if progress_callback is not None:
            progress_callback(
                {
                    "status": "waiting",
                    "reason": last_reason,
                    "expected_source_date": expected_source_date,
                    "pinned_raw_run_id": pinned_run_id,
                    "observed_status": last_status,
                    "raw_status_path": str(status_path),
                    "raw_status_sha256": last_status_sha256,
                    "wait_started_at": started_text,
                    "wait_deadline_at": deadline_text,
                    "wait_seconds": max(0.0, monotonic() - started_mono),
                    "next_action": "wait_for_same_raw_run_or_block_at_deadline",
                }
            )
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        sleep(min(max(0.01, poll_seconds), remaining))

    return blocked(
        "current_stock_cycle_wait_deadline_exhausted"
        if last_reason == "pinned_raw_run_still_running"
        else last_reason
    )
