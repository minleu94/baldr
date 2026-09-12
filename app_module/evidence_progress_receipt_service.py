"""Machine-readable daily/weekly progress for the natural evidence loop.

The receipt is an output-side read model.  It never opens the evidence or
Paper SQLite databases and never creates synthetic observations.  A scheduled
forward run supplies the bounded facts; this module only aggregates receipts
and records whether a new capture was observed since the previous scheduled
run.
"""

from __future__ import annotations

from datetime import date, timedelta
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping


SCHEMA_VERSION = "scheduled-evidence-progress.v1"
TASK_NAME = "baldr-evidence-progress-daily"
NO_NEW_DATA_ALERT_THRESHOLD = 2


def persist_evidence_progress_receipt(
    result: Mapping[str, Any],
    *,
    output_root: str | Path,
) -> dict[str, Any]:
    """Build and persist one idempotent daily/weekly progress receipt."""

    root = Path(output_root).expanduser().resolve()
    progress_dir = root / "scheduled" / "evidence_progress"
    status_path = progress_dir / "latest_status.json"
    run_id = str(result.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("forward result is missing run_id")
    run_path = progress_dir / "runs" / f"{run_id}.json"
    history = _read_history(progress_dir / "runs", exclude_run_id=run_id)
    payload = build_evidence_progress_payload(result, history=history)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

    run_path.parent.mkdir(parents=True, exist_ok=True)
    idempotent = _write_create_only_idempotent(run_path, encoded)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(status_path, encoded)
    return {
        "schema_version": SCHEMA_VERSION,
        "status_path": str(status_path),
        "run_path": str(run_path),
        "idempotent": idempotent,
        "payload": payload,
    }


def build_evidence_progress_payload(
    result: Mapping[str, Any],
    *,
    history: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    """Project bounded forward facts into daily and weekly progress sections."""

    checked_at = str(result.get("checked_at") or "").strip()
    run_date = _date_text(checked_at) or date.today().isoformat()
    current_day = date.fromisoformat(run_date)
    summary = _mapping(result.get("summary"))
    health = _mapping(result.get("health"))
    decision_dates = _decision_dates(health)
    horizons = _horizons(health.get("horizons"))
    calendar_observation = _mapping(result.get("calendar_observation"))
    calendar_state = _calendar_state(calendar_observation)
    calendar_reason = _optional_text(calendar_observation.get("reason_code"))
    if calendar_state is None:
        data_expected = current_day.weekday() < 5
        data_expected_reason = (
            "official_calendar_observation_unknown"
            if calendar_observation
            else "weekday_convention_fallback"
        )
    else:
        data_expected = calendar_state
        data_expected_reason = calendar_reason or "official_calendar_observation"
    calendar_warnings = (
        ["official_calendar_observation_unknown"]
        if calendar_observation and calendar_state is None
        else []
    )
    current_daily: dict[str, Any] = {
        "run_date": run_date,
        "data_expected": data_expected,
        "data_expected_reason": data_expected_reason,
        "calendar_observation": {
            "is_trading_day": calendar_state,
            "reason_code": calendar_reason,
        },
        "status": str(result.get("status") or "unknown"),
        "health_classification": str(health.get("classification") or "unknown"),
        "captures": {
            "events_scanned": _safe_int(summary.get("events_scanned")),
            "qualifying_event_count": _safe_int(health.get("qualifying_event_count")),
            "decision_dates": decision_dates,
            "decision_day_count": len(decision_dates),
            "latest_event_date": _optional_text(health.get("latest_qualifying_event_date")),
            "latest_capture_at": _optional_text(health.get("latest_capture_at")),
        },
        "maturity": {
            "horizons": horizons,
            "ready": _horizon_total(horizons, "ready"),
            "pending": _horizon_total(horizons, "pending"),
            "missing": _horizon_total(horizons, "missing"),
            "outcomes_created": _safe_int(summary.get("outcomes_created")),
            "outcomes_updated": _safe_int(summary.get("outcomes_updated")),
            "next_maturity_date": _optional_text(health.get("next_maturity_date")),
        },
        "blockers": _merge_texts(result.get("blockers"), health.get("blockers")),
        "warnings": _merge_texts(
            result.get("warnings"), health.get("warnings"), calendar_warnings
        ),
        "next_action": _optional_text(result.get("next_action"))
        or _optional_text(health.get("next_action")),
    }

    prior = _latest_prior(history)
    prior_daily = _mapping(prior.get("daily")) if prior else {}
    prior_captures = _mapping(prior_daily.get("captures"))
    current_marker = _capture_marker(current_daily)
    prior_marker = _capture_marker(prior_captures)
    new_data_observed = bool(current_marker) and (
        prior is None or current_marker != prior_marker
    )
    current_daily["captures"]["new_data_observed"] = new_data_observed
    current_daily["captures"]["new_event_count"] = _new_event_count(
        current_daily["captures"], prior_captures
    )

    current_entry = {"run_id": str(result.get("run_id") or ""), "daily": current_daily}
    entries = (*history, current_entry)
    consecutive_no_new = _consecutive_no_new_data(entries)
    if not current_daily["data_expected"]:
        alert_status = "suppressed_non_trading_day"
        alert = False
    elif consecutive_no_new >= NO_NEW_DATA_ALERT_THRESHOLD:
        alert_status = "alert"
        alert = True
    else:
        alert_status = "ok"
        alert = False
    if alert_status == "suppressed_non_trading_day":
        alert_reason = calendar_reason or "non_trading_day"
    elif consecutive_no_new:
        alert_reason = "same_capture_marker"
    else:
        alert_reason = "new_capture_observed"
    no_new_data_alert = {
        "status": alert_status,
        "alert": alert,
        "threshold_days": NO_NEW_DATA_ALERT_THRESHOLD,
        "consecutive_no_new_data_days": consecutive_no_new,
        "last_new_data_run_date": _last_new_data_run_date(entries),
        "reason": alert_reason,
    }
    current_daily["no_new_data_alert"] = no_new_data_alert

    weekly = _weekly_projection(
        current_day=current_day,
        entries=entries,
        current_daily=current_daily,
    )
    blockers = _merge_texts(current_daily["blockers"], weekly["blockers"])
    warnings = _merge_texts(current_daily["warnings"], weekly["warnings"])
    return {
        "schema_version": SCHEMA_VERSION,
        "task": TASK_NAME,
        "run_id": str(result.get("run_id") or ""),
        "checked_at": checked_at,
        "status": str(result.get("status") or "unknown"),
        "source_status_path": _optional_text(result.get("status_path")),
        "daily": current_daily,
        "weekly": weekly,
        "no_new_data_alert": no_new_data_alert,
        "blockers": blockers,
        "warnings": warnings,
        "next_action": current_daily["next_action"]
        or "下一個自然日以相同 bounded window 重跑並觀察新的 capture。",
        "safety_boundary": {
            "research_only": True,
            "historical_backfill": False,
            "writes_evidence_db": False,
            "auto_trading": False,
            "broker_order_allowed": False,
        },
    }


def _weekly_projection(
    *,
    current_day: date,
    entries: tuple[Mapping[str, Any], ...],
    current_daily: Mapping[str, Any],
) -> dict[str, Any]:
    period_start = current_day - timedelta(days=current_day.weekday())
    period_start_text = period_start.isoformat()
    period_end_text = current_day.isoformat()
    selected: list[Mapping[str, Any]] = []
    for entry in entries:
        entry_date = _date_text(_mapping(entry.get("daily")).get("run_date"))
        if entry_date and period_start_text <= entry_date <= period_end_text:
            selected.append(entry)
    observed_run_dates: list[str] = []
    for entry in selected:
        entry_date = _date_text(_mapping(entry.get("daily")).get("run_date"))
        if entry_date and entry_date not in observed_run_dates:
            observed_run_dates.append(entry_date)
    observed_run_dates.sort()
    decision_dates: set[str] = set()
    blockers: list[str] = []
    warnings: list[str] = []
    for entry in selected:
        daily = _mapping(entry.get("daily"))
        captures = _mapping(daily.get("captures"))
        decision_dates.update(_text_dates(captures.get("decision_dates")))
        blockers.extend(_text_items(daily.get("blockers")))
        warnings.extend(_text_items(daily.get("warnings")))
    maturity = _mapping(current_daily.get("maturity"))
    return {
        "period_start": period_start_text,
        "period_end": period_end_text,
        "observed_run_dates": observed_run_dates,
        "observed_run_day_count": len(observed_run_dates),
        "capture_decision_dates": sorted(decision_dates),
        "capture_decision_day_count": len(decision_dates),
        "maturity": {
            "ready": _safe_int(maturity.get("ready")),
            "pending": _safe_int(maturity.get("pending")),
            "missing": _safe_int(maturity.get("missing")),
            "next_maturity_date": _optional_text(maturity.get("next_maturity_date")),
            "horizons": _horizons(maturity.get("horizons")),
        },
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "next_action": _optional_text(current_daily.get("next_action")),
    }


def _capture_marker(value: Mapping[str, Any]) -> tuple[str, tuple[str, ...], int] | tuple[()]:
    captures = _mapping(value.get("captures")) if "captures" in value else value
    latest_capture = _optional_text(captures.get("latest_capture_at"))
    decision_dates = tuple(_text_dates(captures.get("decision_dates")))
    count = _safe_int(captures.get("qualifying_event_count"))
    if not latest_capture and not decision_dates and count == 0:
        return ()
    return latest_capture or "", decision_dates, count


def _new_event_count(current: Mapping[str, Any], prior: Mapping[str, Any]) -> int:
    current_count = _safe_int(current.get("qualifying_event_count"))
    prior_count = _safe_int(prior.get("qualifying_event_count"))
    return max(0, current_count - prior_count)


def _consecutive_no_new_data(entries: tuple[Mapping[str, Any], ...]) -> int:
    by_date: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        daily = _mapping(entry.get("daily"))
        run_date = _date_text(daily.get("run_date"))
        if run_date:
            by_date[run_date] = entry
    total = 0
    for run_date in sorted(by_date, reverse=True):
        daily = _mapping(by_date[run_date].get("daily"))
        if not bool(daily.get("data_expected")):
            continue
        captures = _mapping(daily.get("captures"))
        if bool(captures.get("new_data_observed")):
            break
        total += 1
    return total


def _last_new_data_run_date(entries: tuple[Mapping[str, Any], ...]) -> str | None:
    dates: list[str] = []
    for entry in entries:
        daily = _mapping(entry.get("daily"))
        if bool(_mapping(daily.get("captures")).get("new_data_observed")):
            run_date = _date_text(daily.get("run_date"))
            if run_date:
                dates.append(run_date)
    return max(dates) if dates else None


def _read_history(path: Path, *, exclude_run_id: str) -> tuple[Mapping[str, Any], ...]:
    if not path.is_dir():
        return ()
    values: list[Mapping[str, Any]] = []
    for item in sorted(path.glob("*.json")):
        if item.stem == exclude_run_id:
            continue
        try:
            payload = json.loads(item.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("schema_version") == SCHEMA_VERSION:
            values.append(payload)
    return tuple(values)


def _write_create_only_idempotent(path: Path, text: str) -> bool:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
        return False
    except FileExistsError:
        # A scheduled retry may reuse a timestamp-derived run id.  Keep the
        # first immutable run receipt and refresh only the latest projection.
        existing = path.read_text(encoding="utf-8")
        if not existing.strip():
            raise OSError(f"progress receipt collision is unreadable: {path}")
        return True


def _write_atomic(path: Path, text: str) -> None:
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _horizons(value: object) -> dict[str, dict[str, int]]:
    raw = _mapping(value)
    result: dict[str, dict[str, int]] = {}
    for key, item in raw.items():
        values = _mapping(item)
        result[str(key)] = {
            state: _safe_int(values.get(state)) for state in ("ready", "pending", "missing")
        }
    return result


def _calendar_state(value: Mapping[str, Any]) -> bool | None:
    raw = value.get("is_trading_day")
    return raw if isinstance(raw, bool) else None


def _horizon_total(horizons: Mapping[str, Mapping[str, int]], state: str) -> int:
    return sum(_safe_int(item.get(state)) for item in horizons.values())


def _safe_int(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return max(0, int(str(value)))
    except (TypeError, ValueError):
        return 0


def _optional_text(value: object) -> str | None:
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return None
    text = str(value).strip()
    return text or None


def _date_text(value: object) -> str | None:
    text = _optional_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _text_dates(value: object) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return sorted({parsed for item in value if (parsed := _date_text(item))})


def _decision_dates(health: Mapping[str, Any]) -> list[str]:
    dates: set[str] = set()
    raw_cohorts = health.get("cohorts")
    if isinstance(raw_cohorts, (list, tuple)):
        for item in raw_cohorts:
            dates.update(_text_dates(_mapping(item).get("decision_dates")))
    if not dates:
        latest = _date_text(health.get("latest_qualifying_event_date"))
        if latest:
            dates.add(latest)
    return sorted(dates)


def _text_items(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        values = value
    elif value is None or isinstance(value, Mapping):
        values = ()
    else:
        values = (value,)
    return [text for item in values if (text := str(item).strip())]


def _merge_texts(*values: object) -> list[str]:
    return _dedupe(item for value in values for item in _text_items(value))


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _latest_prior(history: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any] | None:
    if not history:
        return None
    return max(history, key=lambda item: str(item.get("checked_at") or ""))


__all__ = [
    "NO_NEW_DATA_ALERT_THRESHOLD",
    "SCHEMA_VERSION",
    "TASK_NAME",
    "build_evidence_progress_payload",
    "persist_evidence_progress_receipt",
]
