from __future__ import annotations

import json
from pathlib import Path

from app_module.evidence_progress_receipt_service import (
    build_evidence_progress_payload,
    persist_evidence_progress_receipt,
)


def _result(
    *,
    run_id: str,
    checked_at: str,
    decision_dates: list[str] | None = None,
    latest_capture_at: str | None = None,
    qualifying_event_count: int = 0,
    status: str = "passed_with_warnings",
) -> dict[str, object]:
    dates = decision_dates or []
    health = {
        "classification": "waiting_for_natural_maturity",
        "qualifying_event_count": qualifying_event_count,
        "latest_qualifying_event_date": dates[-1] if dates else None,
        "latest_capture_at": latest_capture_at,
        "next_maturity_date": "2026-09-15" if dates else None,
        "blockers": [],
        "warnings": [],
        "next_action": "等待自然成熟",
        "horizons": {
            "5": {"ready": 0, "pending": qualifying_event_count, "missing": 0},
            "20": {"ready": 0, "pending": qualifying_event_count, "missing": 0},
        },
        "cohorts": [{"decision_dates": dates}],
    }
    return {
        "run_id": run_id,
        "checked_at": checked_at,
        "status": status,
        "status_path": "output/scheduled/forward_outcomes/latest_status.json",
        "summary": {
            "events_scanned": qualifying_event_count,
            "outcomes_created": 0,
            "outcomes_updated": 0,
        },
        "health": health,
        "blockers": [],
        "warnings": [],
    }


def test_progress_receipt_projects_daily_and_weekly_natural_facts() -> None:
    payload = build_evidence_progress_payload(
        _result(
            run_id="run-20260910",
            checked_at="2026-09-10T05:40:00+08:00",
            decision_dates=["2026-09-09", "2026-09-10"],
            latest_capture_at="2026-09-10 05:25:49",
            qualifying_event_count=6,
        )
    )

    assert payload["schema_version"] == "scheduled-evidence-progress.v1"
    assert payload["daily"]["captures"]["decision_day_count"] == 2  # type: ignore[index]
    assert payload["daily"]["captures"]["new_data_observed"] is True  # type: ignore[index]
    assert payload["daily"]["maturity"]["pending"] == 12  # type: ignore[index]
    assert payload["weekly"]["capture_decision_day_count"] == 2  # type: ignore[index]
    assert payload["no_new_data_alert"]["alert"] is False  # type: ignore[index]


def test_progress_receipt_alerts_after_two_expected_runs_without_new_capture(tmp_path: Path) -> None:
    root = tmp_path / "output"
    first = persist_evidence_progress_receipt(
        _result(
            run_id="run-20260908",
            checked_at="2026-09-08T05:40:00+08:00",
            decision_dates=["2026-09-08"],
            latest_capture_at="2026-09-08 05:25:49",
            qualifying_event_count=2,
        ),
        output_root=root,
    )
    second = persist_evidence_progress_receipt(
        _result(
            run_id="run-20260909",
            checked_at="2026-09-09T05:40:00+08:00",
            decision_dates=["2026-09-08"],
            latest_capture_at="2026-09-08 05:25:49",
            qualifying_event_count=2,
        ),
        output_root=root,
    )
    third = persist_evidence_progress_receipt(
        _result(
            run_id="run-20260910",
            checked_at="2026-09-10T05:40:00+08:00",
            decision_dates=["2026-09-08"],
            latest_capture_at="2026-09-08 05:25:49",
            qualifying_event_count=2,
        ),
        output_root=root,
    )

    assert Path(first["status_path"]).is_file()
    assert second["payload"]["no_new_data_alert"]["consecutive_no_new_data_days"] == 1  # type: ignore[index]
    assert third["payload"]["no_new_data_alert"]["status"] == "alert"  # type: ignore[index]
    assert third["payload"]["no_new_data_alert"]["alert"] is True  # type: ignore[index]

    latest = json.loads(Path(third["status_path"]).read_text(encoding="utf-8"))
    assert latest["weekly"]["capture_decision_dates"] == ["2026-09-08"]
    assert latest["weekly"]["observed_run_day_count"] == 3


def test_progress_receipt_suppresses_weekend_no_new_alert_and_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "output"
    result = _result(
        run_id="run-20260912",
        checked_at="2026-09-12T05:40:00+08:00",
        decision_dates=["2026-09-11"],
        latest_capture_at="2026-09-11 05:25:49",
        qualifying_event_count=2,
    )
    first = persist_evidence_progress_receipt(result, output_root=root)
    retry = persist_evidence_progress_receipt(result, output_root=root)

    assert first["idempotent"] is False
    assert retry["idempotent"] is True
    assert retry["payload"]["no_new_data_alert"]["status"] == "suppressed_non_trading_day"  # type: ignore[index]
    assert retry["payload"]["no_new_data_alert"]["alert"] is False  # type: ignore[index]


def test_progress_uses_explicit_official_calendar_closed_observation() -> None:
    result = _result(
        run_id="run-20260914",
        checked_at="2026-09-14T05:40:00+08:00",
        decision_dates=["2026-09-11"],
        latest_capture_at="2026-09-11 05:25:49",
        qualifying_event_count=2,
    )
    result["calendar_observation"] = {
        "date": "2026-09-14",
        "is_trading_day": False,
        "reason_code": "twse_holiday_schedule_closed",
    }

    payload = build_evidence_progress_payload(result)

    assert payload["daily"]["data_expected"] is False  # type: ignore[index]
    assert payload["daily"]["data_expected_reason"] == "twse_holiday_schedule_closed"  # type: ignore[index]
    assert payload["no_new_data_alert"]["status"] == "suppressed_non_trading_day"  # type: ignore[index]
    assert payload["no_new_data_alert"]["reason"] == "twse_holiday_schedule_closed"  # type: ignore[index]


def test_progress_does_not_treat_unknown_weekday_calendar_as_closed() -> None:
    result = _result(
        run_id="run-20260914-unknown-calendar",
        checked_at="2026-09-14T05:40:00+08:00",
        decision_dates=["2026-09-11"],
        latest_capture_at="2026-09-11 05:25:49",
        qualifying_event_count=2,
    )
    result["calendar_observation"] = {
        "date": "2026-09-14",
        "is_trading_day": None,
        "reason_code": "official_calendar_observation_unknown",
    }

    payload = build_evidence_progress_payload(result)

    assert payload["daily"]["data_expected"] is True  # type: ignore[index]
    assert "official_calendar_observation_unknown" in payload["warnings"]  # type: ignore[index]
    assert payload["no_new_data_alert"]["status"] == "ok"  # type: ignore[index]
