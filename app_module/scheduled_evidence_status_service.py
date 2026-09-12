from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

from app_module.machine_status_classification import (
    MACHINE_STATUS_HUMAN_REVIEW,
    MACHINE_STATUS_INVALID_EVIDENCE,
    MACHINE_STATUS_MACHINE_CANDIDATE,
    MACHINE_STATUS_MACHINE_DEGRADED,
    MACHINE_STATUS_MACHINE_VERIFIED,
    MACHINE_STATUS_SOURCE_MISSING,
    MACHINE_STATUS_STALE,
    MACHINE_STATUS_UNKNOWN,
    MACHINE_STATUS_WAITING_FOR_TIME,
    classify_machine_status,
)


@dataclass(frozen=True)
class ScheduledEvidenceStatus:
    freshness_status: str = "missing"
    recommendation_status: str = "missing"
    recommendation_source: str = "missing"
    evidence_status: str = "missing"
    latest_data_date: str | None = None
    decision_date: str | None = None
    recommendation_checked_at: str | None = None
    recommendation_result_id: str | None = None
    recommendations_count: int | None = None
    screening_matrix_rows: int | None = None
    why_not_payload_rows: int | None = None
    liquidity_gate_payload_rows: int | None = None
    writes_recommendation_result: bool | None = None
    auto_trading: bool | None = None
    lifecycle_action: bool | None = None
    recommendation_snapshot_observed_days: int = 0
    manual_recommendation_observed_days: int = 0
    evidence_dry_run_observed_days: int = 0
    scheduled_joint_observed_days: int = 0
    scheduled_joint_observed_dates: tuple[str, ...] = ()
    checked_at: str | None = None
    evidence_checked_at: str | None = None
    dry_run: bool | None = None
    confirm: bool | None = None
    writes_evidence_db: bool | None = None
    exit_code: int | None = None
    scheduler_readiness_after: str | None = None
    freshness_warnings: tuple[str, ...] = ()
    freshness_errors: tuple[str, ...] = ()
    source_coverage_warnings: tuple[str, ...] = ()
    pipeline_diagnostic_codes: tuple[str, ...] = ()
    pipeline_blocking_gaps: tuple[str, ...] = ()
    pipeline_overall_status: str | None = None
    pipeline_warnings_count: int | None = None
    pipeline_warning_unique_count: int | None = None
    pipeline_warning_top_counts: tuple[tuple[str, int], ...] = ()
    pipeline_advisories_count: int | None = None
    pipeline_advisory_unique_count: int | None = None
    pipeline_advisory_top_counts: tuple[tuple[str, int], ...] = ()
    report_path: Path | None = None
    log_path: Path | None = None
    manual_recommendation_result_path: Path | None = None
    report_exists: bool = False
    report_preview: str = ""
    diagnostics: tuple[str, ...] = ()
    # These fields describe the read itself.  They are deliberately separate
    # from producer status so a stale last-known-good payload cannot look
    # current merely because its old status was ``passed``.
    load_state: str = "unknown"
    is_stale: bool = False
    load_checked_at: str | None = None
    last_good_loaded_at: str | None = None
    # Forward outcome fields are appended to preserve positional compatibility
    # for older injected DTOs while the read model gains the new receipt.
    forward_outcome_status: str = "missing"
    forward_outcome_checked_at: str | None = None
    forward_outcome_run_id: str | None = None
    forward_outcome_events_scanned: int | None = None
    forward_outcome_outcomes_written: int | None = None
    forward_outcome_pending: int | None = None
    forward_outcome_warnings_count: int | None = None
    forward_outcome_writes_evidence_db: bool | None = None
    forward_outcome_blockers: tuple[str, ...] = ()
    forward_outcome_warnings: tuple[str, ...] = ()
    forward_outcome_status_path: Path | None = None
    # V4 跨日 cohort 健康摘要；欄位追加在 DTO 尾端以維持舊 caller 的 positional 相容。
    forward_health_classification: str | None = None
    forward_health_latest_qualifying_event_date: str | None = None
    forward_health_qualifying_event_count: int | None = None
    forward_health_events_skipped_incomplete_identity: int | None = None
    forward_health_cohort_count: int | None = None
    forward_health_horizons: dict[str, Any] | None = None
    forward_health_latest_capture_at: str | None = None
    forward_health_latest_outcome_updated_at: str | None = None
    forward_health_last_evaluation_at: str | None = None
    forward_health_next_maturity_date: str | None = None
    forward_health_blockers: tuple[str, ...] = ()
    forward_health_warnings: tuple[str, ...] = ()
    forward_health_cohorts: tuple[dict[str, Any], ...] = ()
    forward_health_blocking_reason: str | None = None
    forward_health_next_action: str | None = None
    forward_health_recovery_verification: dict[str, Any] | None = None
    # Daily/weekly progress receipt is an output-side read model.  Keep it at
    # the DTO tail so older positional callers remain compatible.
    evidence_progress_status: str = "missing"
    evidence_progress_checked_at: str | None = None
    evidence_progress_daily: dict[str, Any] | None = None
    evidence_progress_weekly: dict[str, Any] | None = None
    evidence_progress_no_new_data_alert: dict[str, Any] | None = None
    evidence_progress_blockers: tuple[str, ...] = ()
    evidence_progress_warnings: tuple[str, ...] = ()
    evidence_progress_next_action: str | None = None
    evidence_progress_status_path: Path | None = None

    @property
    def has_production_write_risk(self) -> bool:
        return (
            bool(self.confirm)
            or bool(self.writes_evidence_db)
            or bool(self.forward_outcome_writes_evidence_db)
            or bool(self.auto_trading)
            or bool(self.lifecycle_action)
        )

    @property
    def machine_status_classifications(self) -> tuple[tuple[str, str], ...]:
        diagnostics = (
            self.diagnostics
            + self.pipeline_blocking_gaps
            + self.pipeline_diagnostic_codes
            + self.source_coverage_warnings
            + self.freshness_errors
            + self.forward_outcome_blockers
            + self.forward_outcome_warnings
            + self.forward_health_blockers
            + self.forward_health_warnings
            + self.evidence_progress_blockers
            + self.evidence_progress_warnings
        )
        return (
            ("data_freshness", classify_machine_status(self.freshness_status, diagnostics)),
            ("recommendation_snapshot", classify_machine_status(self.recommendation_status, diagnostics)),
            ("evidence_pipeline", classify_machine_status(self.evidence_status, diagnostics)),
            (
                "forward_outcomes",
                _classify_forward_outcome(
                    self.forward_outcome_status,
                    (
                        *self.forward_outcome_blockers,
                        *self.forward_outcome_warnings,
                        *self.forward_health_blockers,
                        *self.forward_health_warnings,
                    ),
                    self.forward_health_classification,
                ),
            ),
        )

    @property
    def machine_status_classification(self) -> str:
        """Return the most conservative machine handling classification."""

        if self.is_stale or self.load_state == MACHINE_STATUS_STALE:
            return MACHINE_STATUS_STALE
        if (
            self.load_state == MACHINE_STATUS_UNKNOWN
            and self.freshness_status in {"", "missing", "unknown"}
            and self.recommendation_status in {"", "missing", "unknown"}
            and self.evidence_status in {"", "missing", "unknown"}
            and self.forward_outcome_status in {"", "missing", "unknown"}
        ):
            return MACHINE_STATUS_UNKNOWN
        classifications = {
            value
            for name, value in self.machine_status_classifications
            if not (
                name == "forward_outcomes"
                and self.forward_outcome_status_path is None
            )
        }
        for value in (
            MACHINE_STATUS_INVALID_EVIDENCE,
            MACHINE_STATUS_SOURCE_MISSING,
            MACHINE_STATUS_WAITING_FOR_TIME,
            MACHINE_STATUS_HUMAN_REVIEW,
            MACHINE_STATUS_MACHINE_CANDIDATE,
            MACHINE_STATUS_MACHINE_DEGRADED,
            MACHINE_STATUS_UNKNOWN,
        ):
            if value in classifications:
                return value
        return MACHINE_STATUS_MACHINE_VERIFIED


class ScheduledEvidenceStatusService:
    """Read-only loader for Windows scheduled evidence output files."""

    def __init__(
        self,
        config: Any,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.output_root = Path(config.output_root)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._last_good_status: ScheduledEvidenceStatus | None = None

    def load_latest(self) -> ScheduledEvidenceStatus:
        checked_at = _timestamp(self._clock())
        try:
            candidate = self._load_latest()
        except Exception as exc:  # noqa: BLE001
            diagnostic = f"status_loader_error:{type(exc).__name__}:{exc}"
            return self._fallback_after_failure(checked_at, (diagnostic,))
        return self._accept_candidate(candidate, checked_at)

    def _load_latest(self) -> ScheduledEvidenceStatus:
        diagnostics: list[str] = []
        freshness_path = self.output_root / "scheduled" / "data_freshness" / "latest_status.json"
        recommendation_path = self.output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
        evidence_path = self.output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json"
        forward_outcome_path = self.output_root / "scheduled" / "forward_outcomes" / "latest_status.json"
        progress_path = self.output_root / "scheduled" / "evidence_progress" / "latest_status.json"
        freshness = _read_json(freshness_path, diagnostics)
        recommendation = _read_json(recommendation_path, diagnostics)
        evidence = _read_json(evidence_path, diagnostics)
        # The outcome producer was added after the existing three scheduled
        # payloads.  Its first absence is an honest source gap, but it must
        # not invalidate a previously observable freshness/recommendation/
        # evidence status during the rollout window.
        forward_outcome = _read_optional_json(forward_outcome_path, diagnostics)
        forward_summary_raw = forward_outcome.get("summary")
        forward_summary: dict[str, Any] = (
            forward_summary_raw if isinstance(forward_summary_raw, dict) else {}
        )
        forward_health_raw = forward_outcome.get("health")
        forward_health: dict[str, Any] = (
            forward_health_raw if isinstance(forward_health_raw, dict) else {}
        )
        forward_health_horizons_raw = forward_health.get("horizons")
        forward_health_horizons = (
            dict(forward_health_horizons_raw)
            if isinstance(forward_health_horizons_raw, dict)
            else None
        )
        progress = _read_optional_json(progress_path, diagnostics)
        progress_daily_raw = progress.get("daily")
        progress_weekly_raw = progress.get("weekly")
        progress_daily = (
            dict(progress_daily_raw) if isinstance(progress_daily_raw, dict) else None
        )
        progress_weekly = (
            dict(progress_weekly_raw) if isinstance(progress_weekly_raw, dict) else None
        )
        progress_alert_raw = progress.get("no_new_data_alert")
        progress_alert = (
            dict(progress_alert_raw) if isinstance(progress_alert_raw, dict) else None
        )
        progress_alert_warning = (
            ("evidence_progress_no_new_data_consecutive",)
            if progress_alert and bool(progress_alert.get("alert"))
            else ()
        )

        report_path = _optional_path(evidence.get("report_path"))
        log_path = _optional_path(evidence.get("log_path"))
        report_preview = ""
        report_exists = bool(report_path and report_path.exists())
        if report_path is not None and report_exists:
            report_preview = _read_report_preview(report_path, diagnostics)
        elif report_path is not None:
            diagnostics.append(f"report_missing:{report_path}")

        checks_raw = freshness.get("checks")
        checks: dict[str, Any] = checks_raw if isinstance(checks_raw, dict) else {}
        latest_data_date = (
            checks.get("daily_prices_latest_date")
            or checks.get("daily_price_latest_date_key")
            or checks.get("technical_indicators_latest_date")
        )
        decision_date_key = _date_key(evidence.get("decision_date")) or _date_key(latest_data_date)
        manual_recommendation: dict[str, Any] = {}
        manual_recommendation_path: Path | None = None
        if not recommendation:
            manual_recommendation, manual_recommendation_path = _latest_manual_recommendation_result(
                self.output_root,
                decision_date_key,
                diagnostics,
            )
        recommendation_payload = recommendation or manual_recommendation
        recommendation_source = (
            "scheduled_latest_status"
            if recommendation
            else "manual_result"
            if manual_recommendation
            else "missing"
        )
        recommendation_status = (
            str(recommendation.get("status") or "missing") if recommendation else "manual_observed" if manual_recommendation else "missing"
        )
        recommendation_dates = _scheduled_recommendation_dates(self.output_root)
        manual_recommendation_dates = _manual_recommendation_dates(self.output_root)
        evidence_dates = _scheduled_evidence_report_dates(self.output_root)
        for raw_date in (recommendation.get("decision_date"), evidence.get("decision_date")):
            date_key = _date_key(raw_date)
            if date_key and raw_date == recommendation.get("decision_date"):
                recommendation_dates.add(date_key)
            if date_key and raw_date == evidence.get("decision_date"):
                evidence_dates.add(date_key)
        joint_dates = tuple(sorted(recommendation_dates & evidence_dates))

        return ScheduledEvidenceStatus(
            freshness_status=str(freshness.get("status") or "missing"),
            recommendation_status=recommendation_status,
            recommendation_source=recommendation_source,
            evidence_status=str(evidence.get("status") or "missing"),
            forward_outcome_status=str(forward_outcome.get("status") or "missing"),
            latest_data_date=str(latest_data_date) if latest_data_date else None,
            decision_date=_str_or_none(evidence.get("decision_date")),
            recommendation_checked_at=_str_or_none(
                recommendation_payload.get("checked_at") or recommendation_payload.get("created_at")
            ),
            forward_outcome_checked_at=_str_or_none(forward_outcome.get("checked_at")),
            recommendation_result_id=_str_or_none(recommendation_payload.get("result_id")),
            forward_outcome_run_id=_str_or_none(forward_outcome.get("run_id")),
            recommendations_count=_count_or_int(
                recommendation_payload.get("recommendations_count"),
                recommendation_payload.get("recommendations"),
            ),
            forward_outcome_events_scanned=_int_or_none(forward_summary.get("events_scanned")),
            forward_outcome_outcomes_written=_int_or_none(forward_summary.get("outcomes_written")),
            forward_outcome_pending=_int_or_none(
                forward_summary.get("pending_insufficient_future_data")
            ),
            forward_outcome_warnings_count=_int_or_none(forward_summary.get("warnings_count")),
            screening_matrix_rows=_count_or_int(
                recommendation_payload.get("screening_matrix_rows"),
                recommendation_payload.get("screening_matrix_json"),
            ),
            why_not_payload_rows=_count_or_int(
                recommendation_payload.get("why_not_payload_rows"),
                recommendation_payload.get("why_not_payload_json"),
            ),
            liquidity_gate_payload_rows=_count_or_int(
                recommendation_payload.get("liquidity_gate_payload_rows"),
                recommendation_payload.get("liquidity_gate_payload_json"),
            ),
            writes_recommendation_result=_bool_or_none(
                recommendation_payload.get("writes_recommendation_result")
                if recommendation
                else bool(manual_recommendation)
            ),
            auto_trading=_bool_or_none(recommendation_payload.get("auto_trading") if recommendation else False),
            lifecycle_action=_bool_or_none(recommendation_payload.get("lifecycle_action") if recommendation else False),
            recommendation_snapshot_observed_days=len(recommendation_dates),
            manual_recommendation_observed_days=len(manual_recommendation_dates),
            evidence_dry_run_observed_days=len(evidence_dates),
            scheduled_joint_observed_days=len(joint_dates),
            scheduled_joint_observed_dates=joint_dates,
            checked_at=_str_or_none(freshness.get("checked_at")),
            evidence_checked_at=_str_or_none(evidence.get("checked_at")),
            dry_run=_bool_or_none(evidence.get("dry_run")),
            confirm=_merged_bool(evidence.get("confirm"), recommendation_payload.get("confirm") if recommendation else False),
            writes_evidence_db=_merged_bool(
                evidence.get("writes_evidence_db"),
                recommendation_payload.get("writes_evidence_db") if recommendation else False,
            ),
            exit_code=_int_or_none(evidence.get("exit_code")),
            scheduler_readiness_after=_str_or_none(evidence.get("scheduler_readiness_after")),
            freshness_warnings=_tuple_of_str(freshness.get("warnings")),
            freshness_errors=_tuple_of_str(freshness.get("errors")),
            source_coverage_warnings=_tuple_of_str(evidence.get("source_coverage_warnings")),
            pipeline_diagnostic_codes=_tuple_of_str(evidence.get("pipeline_diagnostic_codes")),
            pipeline_blocking_gaps=_tuple_of_str(evidence.get("pipeline_blocking_gaps")),
            pipeline_overall_status=_str_or_none(evidence.get("pipeline_overall_status")),
            pipeline_warnings_count=_int_or_none(evidence.get("pipeline_warnings_count")),
            pipeline_warning_unique_count=_int_or_none(evidence.get("pipeline_warning_unique_count")),
            pipeline_warning_top_counts=_warning_top_counts(evidence.get("pipeline_warning_top_counts")),
            pipeline_advisories_count=_int_or_none(evidence.get("pipeline_advisories_count")),
            pipeline_advisory_unique_count=_int_or_none(evidence.get("pipeline_advisory_unique_count")),
            pipeline_advisory_top_counts=_advisory_top_counts(evidence.get("pipeline_advisory_top_counts")),
            report_path=report_path,
            log_path=log_path,
            manual_recommendation_result_path=manual_recommendation_path,
            forward_outcome_status_path=forward_outcome_path if forward_outcome else None,
            report_exists=report_exists,
            report_preview=report_preview,
            diagnostics=tuple(diagnostics),
            forward_outcome_writes_evidence_db=_bool_or_none(
                forward_outcome.get("writes_evidence_db")
            ),
            forward_outcome_blockers=_tuple_of_str(forward_outcome.get("blockers")),
            forward_outcome_warnings=_tuple_of_str(forward_outcome.get("warnings")),
            forward_health_classification=_str_or_none(forward_health.get("classification")),
            forward_health_latest_qualifying_event_date=_str_or_none(
                forward_health.get("latest_qualifying_event_date")
            ),
            forward_health_qualifying_event_count=_int_or_none(
                forward_health.get("qualifying_event_count")
            ),
            forward_health_events_skipped_incomplete_identity=_int_or_none(
                forward_health.get("events_skipped_incomplete_identity")
            ),
            forward_health_cohort_count=_int_or_none(forward_health.get("cohort_count")),
            forward_health_horizons=forward_health_horizons,
            forward_health_latest_capture_at=_str_or_none(
                forward_health.get("latest_capture_at")
            ),
            forward_health_latest_outcome_updated_at=_str_or_none(
                forward_health.get("latest_outcome_updated_at")
            ),
            forward_health_last_evaluation_at=_str_or_none(
                forward_health.get("last_evaluation_at")
            ),
            forward_health_next_maturity_date=_str_or_none(
                forward_health.get("next_maturity_date")
            ),
            forward_health_blockers=_tuple_of_str(forward_health.get("blockers")),
            forward_health_warnings=_tuple_of_str(forward_health.get("warnings")),
            forward_health_cohorts=tuple(
                item
                for item in (forward_health.get("cohorts") or ())
                if isinstance(item, dict)
            ),
            forward_health_blocking_reason=_str_or_none(
                forward_health.get("blocking_reason")
            ),
            forward_health_next_action=_str_or_none(forward_health.get("next_action")),
            forward_health_recovery_verification=(
                dict(forward_health["recovery_verification"])
                if isinstance(forward_health.get("recovery_verification"), dict)
                else None
            ),
            evidence_progress_status=str(progress.get("status") or "missing"),
            evidence_progress_checked_at=_str_or_none(progress.get("checked_at")),
            evidence_progress_daily=progress_daily,
            evidence_progress_weekly=progress_weekly,
            evidence_progress_no_new_data_alert=progress_alert,
            evidence_progress_blockers=_tuple_of_str(progress.get("blockers")),
            evidence_progress_warnings=_dedupe_strings(
                (*_tuple_of_str(progress.get("warnings")), *progress_alert_warning)
            ),
            evidence_progress_next_action=_str_or_none(progress.get("next_action")),
            evidence_progress_status_path=progress_path if progress else None,
        )

    def _accept_candidate(
        self,
        candidate: ScheduledEvidenceStatus,
        checked_at: str,
    ) -> ScheduledEvidenceStatus:
        failures = tuple(
            diagnostic
            for diagnostic in candidate.diagnostics
            if diagnostic.startswith(
                ("status_missing:", "status_unreadable:", "status_invalid_payload:")
            )
        )
        if (
            candidate.freshness_status in {"", "missing", "unknown"}
            and candidate.recommendation_status in {"", "missing", "unknown"}
            and candidate.evidence_status in {"", "missing", "unknown"}
            and candidate.forward_outcome_status in {"", "missing", "unknown"}
        ):
            failures = (*failures, "status_no_observation")

        if failures:
            return self._fallback_after_failure(checked_at, failures, candidate)

        current = replace(
            candidate,
            load_state="current",
            is_stale=False,
            load_checked_at=checked_at,
            last_good_loaded_at=checked_at,
        )
        self._last_good_status = current
        return current

    def _fallback_after_failure(
        self,
        checked_at: str,
        failures: tuple[str, ...],
        candidate: ScheduledEvidenceStatus | None = None,
    ) -> ScheduledEvidenceStatus:
        if self._last_good_status is not None:
            previous = self._last_good_status
            last_good_at = previous.last_good_loaded_at or previous.load_checked_at
            diagnostics = _dedupe_strings(
                (
                    *previous.diagnostics,
                    *(candidate.diagnostics if candidate is not None else ()),
                    *failures,
                    "last_known_good_preserved",
                )
            )
            return replace(
                previous,
                load_state="stale",
                is_stale=True,
                load_checked_at=checked_at,
                last_good_loaded_at=last_good_at,
                diagnostics=diagnostics,
            )

        base = candidate or ScheduledEvidenceStatus()
        diagnostics = _dedupe_strings((*base.diagnostics, *failures))
        return replace(
            base,
            load_state="unknown",
            is_stale=False,
            load_checked_at=checked_at,
            last_good_loaded_at=None,
            diagnostics=diagnostics,
        )


def _classify_forward_outcome(
    status: object,
    diagnostics: tuple[str, ...],
    health_classification: str | None = None,
) -> str:
    """Project producer-specific states onto the shared machine vocabulary."""

    health = str(health_classification or "").strip().lower()
    if health == "actionable_engineering_blocker":
        return MACHINE_STATUS_INVALID_EVIDENCE
    if health == "external_source_missing":
        return MACHINE_STATUS_SOURCE_MISSING
    if health == "waiting_for_natural_maturity":
        return MACHINE_STATUS_WAITING_FOR_TIME
    raw = str(status or "").strip().lower()
    if raw in {"passed_with_warnings", "degraded", "warning", "partial"}:
        return MACHINE_STATUS_MACHINE_DEGRADED
    if raw == "dry_run":
        return MACHINE_STATUS_MACHINE_CANDIDATE
    if raw in {"blocked", "failed", "error"}:
        return MACHINE_STATUS_INVALID_EVIDENCE
    return classify_machine_status(raw, diagnostics)


def _read_json(path: Path, diagnostics: list[str]) -> dict[str, Any]:
    if not path.exists():
        diagnostics.append(f"status_missing:{path}")
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        diagnostics.append(f"status_unreadable:{path}:{exc}")
        return {}
    if not isinstance(loaded, dict):
        diagnostics.append(f"status_invalid_payload:{path}:expected_object")
        return {}
    return loaded


def _read_optional_json(path: Path, diagnostics: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_json(path, diagnostics)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _dedupe_strings(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)


def _read_report_preview(path: Path, diagnostics: list[str], *, max_lines: int = 120) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        diagnostics.append(f"report_unreadable:{path}:{exc}")
        return ""
    return "\n".join(lines[:max_lines])


def _optional_path(value: Any) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    return Path(str(value))


def _scheduled_recommendation_dates(output_root: Path) -> set[str]:
    runs_dir = output_root / "recommendation" / "runs"
    dates: set[str] = set()
    if not runs_dir.exists():
        return dates
    for path in runs_dir.glob("scheduled_rec_*.json"):
        parts = path.stem.split("_")
        if len(parts) >= 3 and len(parts[2]) == 8 and parts[2].isdigit():
            dates.add(parts[2])
    return dates


def _manual_recommendation_dates(output_root: Path) -> set[str]:
    runs_dir = output_root / "recommendation" / "runs"
    dates: set[str] = set()
    if not runs_dir.exists():
        return dates
    for path in runs_dir.glob("rec_*.json"):
        parts = path.stem.split("_")
        if len(parts) >= 3 and len(parts[1]) == 8 and parts[1].isdigit():
            dates.add(parts[1])
    return dates


def _latest_manual_recommendation_result(
    output_root: Path,
    date_key: str | None,
    diagnostics: list[str],
) -> tuple[dict[str, Any], Path | None]:
    if not date_key:
        return {}, None
    runs_dir = output_root / "recommendation" / "runs"
    if not runs_dir.exists():
        return {}, None
    candidates = sorted(runs_dir.glob(f"rec_{date_key}_*.json"), key=lambda path: path.name, reverse=True)
    for path in candidates:
        payload = _read_json(path, diagnostics)
        if payload:
            diagnostics.append(f"manual_recommendation_result_observed:{path}")
            return payload, path
    return {}, None


def _scheduled_evidence_report_dates(output_root: Path) -> set[str]:
    report_dir = output_root / "scheduled" / "evidence_pipeline_dry_run" / "reports"
    dates: set[str] = set()
    if not report_dir.exists():
        return dates
    for path in report_dir.glob("*_evidence_pipeline_dry_run.md"):
        prefix = path.name.split("_", 1)[0]
        if len(prefix) == 8 and prefix.isdigit():
            dates.add(prefix)
    return dates


def _date_key(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    compact = text.replace("-", "")
    if len(compact) == 8 and compact.isdigit():
        return compact
    return None


def _tuple_of_str(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return (str(value),)


def _warning_top_counts(value: Any) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    rows: list[tuple[str, int]] = []
    for item in value:
        warning: str
        raw_count: Any
        if isinstance(item, dict):
            warning = str(item.get("warning") or "").strip()
            raw_count = item.get("count")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            warning = str(item[0] or "").strip()
            raw_count = item[1]
        else:
            continue
        count = _int_or_none(raw_count)
        if warning and count is not None:
            rows.append((warning, count))
    return tuple(rows)


def _advisory_top_counts(value: Any) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    rows: list[tuple[str, int]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        advisory = str(item.get("advisory") or "").strip()
        count = _int_or_none(item.get("count"))
        if advisory and count is not None and count > 0:
            rows.append((advisory, count))
    return tuple(rows)


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
        return None
    return bool(value)


def _merged_bool(*values: Any) -> bool | None:
    parsed = [_bool_or_none(value) for value in values if value is not None]
    if not parsed:
        return None
    return any(parsed)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _count_or_int(value: Any, rows: Any) -> int | None:
    parsed = _int_or_none(value)
    if parsed is not None:
        return parsed
    if isinstance(rows, (list, tuple)):
        return len(rows)
    return None
