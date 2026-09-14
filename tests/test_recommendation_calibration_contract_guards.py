from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
import subprocess

import pytest

from data_module.recommendation_calibration_source_contract import (
    _availability_before_or_at,
    _aware_datetime,
)
from ml_module.recommendation_calibration_evidence import (
    _hash_payload,
    _sha256_file,
    _verify_source_availability,
    _verify_source_contract_binding,
)
from ml_module.recommendation_historical_replay import _time_stratified_eligible_dates
from scripts.scheduled import run_daily_recommendation_learning as daily_learning
from scripts.scheduled import run_daily_recommendation_learning_pipeline as pipeline


def _availability_contract(*, event_available_at: str) -> tuple[dict[str, object], dict[str, object]]:
    feature_snapshot = {
        "content_sha256": "sha256:" + "f" * 64,
        "captured_at": "2026-09-14T17:00:00+08:00",
    }
    technical = {
        "publication_available_at": "2026-09-14T17:00:00+08:00",
        "source_receipt_available_ats": ["2026-09-14T09:00:00Z"],
        "prospective_feature_snapshot": feature_snapshot,
    }
    contract = {
        "technical": technical,
        "corporate_actions": {
            "adjustment_custody": {
                "available_at": "2026-09-14T17:00:00+08:00",
            },
            "event_publication": {
                "source_publication_available_at": event_available_at,
            },
        },
    }
    binding = {
        "technical_publication_available_at": technical["publication_available_at"],
        "technical_source_available_ats": list(technical["source_receipt_available_ats"]),
        "feature_snapshot_captured_at": feature_snapshot["captured_at"],
        "corporate_adjustment_available_at": "2026-09-14T17:00:00+08:00",
        "official_event_available_at": event_available_at,
    }
    return contract, binding


def test_source_availability_accepts_same_instant_across_timezones() -> None:
    cutoff = _aware_datetime("2026-09-14T17:00:00+08:00")
    assert cutoff is not None
    assert _availability_before_or_at("2026-09-14T09:00:00Z", cutoff)
    contract, binding = _availability_contract(
        event_available_at="2026-09-14T09:00:00Z",
    )

    _verify_source_availability(
        contract,
        binding,
        capture_at="2026-09-14T09:00:00+00:00",
    )


def test_source_availability_rejects_late_same_day_publication() -> None:
    cutoff = _aware_datetime("2026-09-14T17:00:00+08:00")
    assert cutoff is not None
    assert not _availability_before_or_at("2026-09-14T17:00:01+08:00", cutoff)
    contract, binding = _availability_contract(
        event_available_at="2026-09-14T17:00:01+08:00",
    )

    with pytest.raises(ValueError, match="available after capture cutoff"):
        _verify_source_availability(
            contract,
            binding,
            capture_at="2026-09-14T09:00:00Z",
        )


def test_missing_feature_snapshot_cannot_be_skipped(tmp_path: Path) -> None:
    contract_body = {
        "schema_version": "recommendation-calibration-source-contract.v1",
        "decision_date": "2026-09-14",
        "symbols": ["1101"],
        "lanes": {
            "price_up_calibration": {
                "prospective_status": "ready",
            },
        },
        "technical": {},
    }
    contract_payload = {
        **contract_body,
        "contract_sha256": _hash_payload(contract_body),
        "checked_at": "2026-09-14T09:00:00Z",
    }
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(
        json.dumps(contract_payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    binding = {
        "schema_version": "recommendation-calibration-capture-source-binding.v1",
        "contract_path": str(contract_path),
        "contract_content_sha256": contract_payload["contract_sha256"],
        "contract_file_sha256": _sha256_file(contract_path),
        "decision_date": "2026-09-14",
        "symbols": ["1101"],
        "price_up_prospective_status": "ready",
        "historical_pit_eligible": False,
    }

    with pytest.raises(ValueError, match="feature snapshot missing"):
        _verify_source_contract_binding(
            binding,
            require_ready=True,
            capture_at="2026-09-14T09:00:00Z",
        )


def test_pipeline_child_timeout_is_recoverable(monkeypatch, tmp_path: Path) -> None:
    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            kwargs.get("args") or args[0],
            kwargs.get("timeout"),
            output="partial output",
            stderr="partial error",
        )

    monkeypatch.setattr(pipeline.subprocess, "run", _timeout)
    result = pipeline._run_child(
        name="recommendation_snapshot",
        script="scripts/scheduled/run_scheduled_recommendation_snapshot.py",
        arguments=[],
        environment={"RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(tmp_path)},
        log_handle=StringIO(),
        timeout_seconds=1.0,
    )

    assert result["status"] == "timed_out"
    assert result["recoverable"] is True
    assert result["returncode"] is None
    assert result["child_blockers"] == ["subprocess_timeout:recommendation_snapshot"]


def test_pipeline_unknown_failed_training_status_fails_closed(monkeypatch, tmp_path: Path) -> None:
    status_path = tmp_path / "recommendation_learning" / "latest_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps({"status": "failed_training", "warnings": [], "blockers": []}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        pipeline.subprocess,
        "run",
        lambda *args, **kwargs: type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "", "stderr": ""},
        )(),
    )
    result = pipeline._run_child(
        name="recommendation_learning",
        script="scripts/scheduled/run_daily_recommendation_learning.py",
        arguments=[],
        environment={"RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(tmp_path)},
        log_handle=StringIO(),
        timeout_seconds=1.0,
    )

    assert result["status"] == "failed"
    assert result["child_status"]["status"] == "failed_training"


def test_nested_blocked_live_capture_is_recoverable_pipeline_failure(
    monkeypatch, tmp_path: Path
) -> None:
    status_path = tmp_path / "recommendation_learning" / "latest_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(
            {
                "status": "completed",
                "warnings": [],
                "blockers": [],
                "live_capture": {
                    "status": "blocked",
                    "reason": "technical_prospective_source_not_ready",
                    "capture_path": None,
                },
                "cli_recoverable": True,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        pipeline.subprocess,
        "run",
        lambda *args, **kwargs: type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "", "stderr": ""},
        )(),
    )
    result = pipeline._run_child(
        name="recommendation_learning",
        script="scripts/scheduled/run_daily_recommendation_learning.py",
        arguments=[],
        environment={"RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(tmp_path)},
        log_handle=StringIO(),
        timeout_seconds=1.0,
    )

    assert result["status"] == "failed"
    assert result["recoverable"] is True
    assert result["child_blockers"] == [
        "live_capture_blocked:technical_prospective_source_not_ready"
    ]


def test_natural_pending_capture_skip_is_not_a_pipeline_error(
    monkeypatch, tmp_path: Path
) -> None:
    status_path = tmp_path / "recommendation_learning" / "latest_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(
            {
                "status": "completed",
                "warnings": [],
                "blockers": [],
                "live_capture": {
                    "status": "skipped",
                    "reason": "non_trading_day_official_calendar",
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        pipeline.subprocess,
        "run",
        lambda *args, **kwargs: type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "", "stderr": ""},
        )(),
    )
    result = pipeline._run_child(
        name="recommendation_learning",
        script="scripts/scheduled/run_daily_recommendation_learning.py",
        arguments=[],
        environment={"RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(tmp_path)},
        log_handle=StringIO(),
        timeout_seconds=1.0,
    )

    assert result["status"] == "passed"
    assert result["child_blockers"] == []
    assert result["recoverable"] is False


def test_learning_capture_dependency_classifier_preserves_natural_skips() -> None:
    assert daily_learning._capture_dependency_failure(
        {
            "status": "blocked",
            "reason": "prospective_source_contract_not_ready",
        }
    ) == (
        "live_capture_blocked:prospective_source_contract_not_ready",
        True,
    )
    assert daily_learning._capture_dependency_failure(
        {"status": "skipped", "reason": "natural_forward_evidence_pending"}
    ) == (None, False)


def test_time_stratified_replay_selection_is_deterministic_and_maturable_only() -> None:
    candidates = tuple(f"2026-01-{day:02d}" for day in range(1, 29))

    selected = _time_stratified_eligible_dates(
        candidates,
        max_decision_dates=5,
        horizon_trading_days=20,
    )

    assert selected == (
        "2026-01-01",
        "2026-01-02",
        "2026-01-04",
        "2026-01-06",
        "2026-01-08",
    )
    assert selected == _time_stratified_eligible_dates(
        candidates,
        max_decision_dates=5,
        horizon_trading_days=20,
    )
    assert max(selected) == candidates[-21]
