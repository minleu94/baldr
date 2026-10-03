from __future__ import annotations

import io
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from types import SimpleNamespace

import pytest

from scripts.scheduled import run_scheduled_evidence_pipeline_dry_run
from app_module import exit_effectiveness_producer as exit_producer


def _canonical_exit_json(payload: object) -> str:
    return exit_producer._canonical_json(payload)


def _exit_effectiveness_payload(*, generated_at: datetime) -> dict[str, object]:
    taipei_date = generated_at.astimezone(timezone(timedelta(hours=8))).date()
    payload = exit_producer._base_payload(now=generated_at, as_of_date=taipei_date)
    payload["status"] = "passed"
    payload["evidence_hash"] = exit_producer._sha256_json(payload)
    return payload


def _fake_exit_effectiveness_stdout(
    *, output_path: Path, generated_at: datetime
) -> dict[str, object]:
    payload = _exit_effectiveness_payload(generated_at=generated_at)
    encoded = (_canonical_exit_json(payload) + "\n").encode("utf-8")
    artifact_path, write_status = exit_producer._create_only(output_path, encoded)
    payload["artifact_path"] = str(artifact_path)
    payload["artifact_write_status"] = write_status
    payload["artifact_file_sha256"] = exit_producer._sha256(encoded)
    return payload


def _binding_fixture(tmp_path, monkeypatch):
    runner = run_scheduled_evidence_pipeline_dry_run
    now = datetime(2026, 9, 29, 5, 15, tzinfo=ZoneInfo("America/Los_Angeles"))
    path = tmp_path / "scheduled" / "recommendation_snapshot" / "latest_status.json"
    path.parent.mkdir(parents=True)
    payload = {
        "task": "baldr-recommendation-snapshot-daily", "status": "passed",
        "decision_date": "2026-09-29", "checked_at": "2026-09-29T05:10:00-07:00",
        "output_root": str(tmp_path), "result_id": "canonical-same-day",
        "writes_recommendation_result": True, "writes_evidence_db": False,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    model = SimpleNamespace(
        result_id="canonical-same-day", persisted_at=now,
        payload_hash="sha256:" + "a" * 64,
    )

    class Queries:
        def get(self, result_id):
            assert result_id == "canonical-same-day"
            return model

        def list(self):
            pytest.fail("scheduled source must never guess mixed latest")

    monkeypatch.setattr(runner, "build_recommendation_execution_queries", lambda config: Queries())
    monkeypatch.setattr(runner, "canonical_scheduled_decision_date", lambda item: "2026-09-29")
    return now, path, payload, model


def test_binding_uses_exact_canonical_id_not_mixed_latest(tmp_path, monkeypatch):
    now, path, _payload, _model = _binding_fixture(tmp_path, monkeypatch)
    binding = run_scheduled_evidence_pipeline_dry_run._scheduled_recommendation_binding(
        tmp_path, decision_date="2026-09-29", observed_at=now,
    )
    assert binding["result_id"] == "canonical-same-day"
    assert binding["status_path"] == str(path.resolve())
    assert binding["status_sha256"].startswith("sha256:")


@pytest.mark.parametrize("changes", [
    {"decision_date": "2026-09-28"}, {"status": "running"},
    {"writes_recommendation_result": False}, {"output_root": "other-root"},
    {"checked_at": "2026-09-29T05:10:00"},
    {"checked_at": "2026-09-29T05:16:00-07:00"},
    {"checked_at": "2026-09-28T05:10:00-07:00"}, {"result_id": ""},
])
def test_binding_rejects_stale_unproven_or_future_status(tmp_path, monkeypatch, changes):
    now, path, payload, _model = _binding_fixture(tmp_path, monkeypatch)
    payload.update(changes)
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        run_scheduled_evidence_pipeline_dry_run._scheduled_recommendation_binding(
            tmp_path, decision_date="2026-09-29", observed_at=now,
        )


def test_binding_rejects_missing_canonical_or_future_persistence(tmp_path, monkeypatch):
    runner = run_scheduled_evidence_pipeline_dry_run
    now, _path, _payload, model = _binding_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "canonical_scheduled_decision_date", lambda item: None)
    with pytest.raises(ValueError, match="canonical_identity_mismatch"):
        runner._scheduled_recommendation_binding(tmp_path, decision_date="2026-09-29", observed_at=now)
    monkeypatch.setattr(runner, "canonical_scheduled_decision_date", lambda item: "2026-09-29")
    model.persisted_at = datetime(2026, 9, 30, tzinfo=ZoneInfo("America/Los_Angeles"))
    with pytest.raises(ValueError, match="persisted_clock_invalid"):
        runner._scheduled_recommendation_binding(tmp_path, decision_date="2026-09-29", observed_at=now)


def test_binding_missing_stops_before_any_child_and_records_failure(tmp_path, monkeypatch):
    runner = run_scheduled_evidence_pipeline_dry_run
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("child must not start"))
    assert runner.main([
        "--dry-run", "--bind-scheduled-recommendation", "--data-root", str(tmp_path / "data"),
        "--output-root", str(tmp_path), "--db-path", str(tmp_path / "market.db"),
    ]) == 2
    payload = json.loads((tmp_path / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json").read_text(encoding="utf-8"))
    assert payload["pipeline_execution_started"] is False
    assert payload["writes_evidence_db"] is False
    assert payload["manual_action_required"] is True


def test_binding_is_forwarded_and_timeout_preserves_partial_output(tmp_path, monkeypatch):
    runner = run_scheduled_evidence_pipeline_dry_run
    now, _path, _payload, _model = _binding_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "scheduled_now", lambda: now)

    def child(command, **kwargs):
        assert command[command.index("--result-id") + 1] == "canonical-same-day"
        assert kwargs["timeout"] == 600
        raise subprocess.TimeoutExpired(command, 600, output=b"partial output")

    monkeypatch.setattr(subprocess, "run", child)
    assert runner.main([
        "--dry-run", "--bind-scheduled-recommendation", "--data-root", str(tmp_path / "data"),
        "--output-root", str(tmp_path), "--db-path", str(tmp_path / "market.db"),
    ]) == 2
    payload = json.loads((tmp_path / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json").read_text(encoding="utf-8"))
    assert payload["recommendation_binding"]["result_id"] == "canonical-same-day"
    assert payload["pipeline_execution_error"] == "evidence_pipeline_child_timeout"
    assert Path(payload["log_path"]).read_text(encoding="utf-8") == "partial output"


def test_scheduled_wrapper_stdout_survives_cp1252_console_with_chinese_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "輸出"
    db_path = tmp_path / "資料" / "sqlite" / "twstock.db"

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args, returncode=0, stdout='{"overall_status":"passed","warnings":[]}\n')

    output_buffer = io.BytesIO()
    stdout = io.TextIOWrapper(output_buffer, encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(subprocess, "run", fake_run)

    exit_code = run_scheduled_evidence_pipeline_dry_run.main(
        [
            "--dry-run",
            "--data-root",
            str(tmp_path / "資料"),
            "--output-root",
            str(output_root),
            "--db-path",
            str(db_path),
            "--sources",
            "all",
        ]
    )

    stdout.flush()
    raw_output = output_buffer.getvalue().decode("cp1252")
    payload = json.loads(raw_output)
    assert exit_code == 0
    assert payload["db_path"] == str(db_path)
    assert payload["confirm"] is False
    assert payload["production_scheduler_allowed"] is False
    assert payload["manual_action_required"] is True
    assert "輸出" in payload["report_path"]
    assert "\\u8f38\\u51fa" in raw_output
    assert (output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json").exists()


def test_scheduled_wrapper_persists_pipeline_source_coverage_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    db_path = tmp_path / "data" / "sqlite" / "twstock.db"
    paper_operation_root = tmp_path / "paper-operation"
    paper_health_baseline = tmp_path / "health" / "baseline.json"
    paper_status_path = tmp_path / "paper-status.json"
    freshness_status_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness_status_path.parent.mkdir(parents=True)
    freshness_status_path.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    pipeline_summary = {
        "overall_status": "degraded",
        "warnings_count": 3,
        "warning_counts": {"screening_matrix_missing": 2, "diagnostic:source_missing_screening_matrix": 1},
        "errors_count": 0,
        "blocking_gaps": [],
        "diagnostic_codes": ["source_missing_screening_matrix"],
        "scheduler_readiness_before": "dry_run_only",
        "scheduler_readiness_after": "ready_for_manual_confirm",
        "source_coverage": {
            "warnings": ["screening_matrix_missing"],
            "blocking_gaps": [],
            "recommendation_screening_matrix_available": False,
            "recommendation_exclusion_payload_available": True,
            "source_coverage_basis": "dry_run_transient_decision_desk_snapshot",
        },
    }

    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = args[0]
        stdout = "config log before json\n" + json.dumps(pipeline_summary)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    exit_code = run_scheduled_evidence_pipeline_dry_run.main(
        [
            "--dry-run",
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--db-path",
            str(db_path),
            "--sources",
            "all",
            "--paper-evidence-operation-root",
            str(paper_operation_root),
            "--paper-evidence-health-baseline",
            str(paper_health_baseline),
            "--paper-evidence-status-path",
            str(paper_status_path),
        ]
    )

    status_path = output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json"
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "degraded"
    assert payload["pipeline_overall_status"] == "degraded"
    assert payload["pipeline_summary_available"] is True
    assert payload["pipeline_warning_counts"] == {
        "diagnostic:source_missing_screening_matrix": 1,
        "screening_matrix_missing": 2,
    }
    assert payload["pipeline_warning_unique_count"] == 2
    assert payload["pipeline_warning_top_counts"] == [
        {"warning": "screening_matrix_missing", "count": 2},
        {"warning": "diagnostic:source_missing_screening_matrix", "count": 1},
    ]
    assert payload["pipeline_diagnostic_codes"] == ["source_missing_screening_matrix"]
    assert payload["source_coverage_warnings"] == ["screening_matrix_missing"]
    assert payload["recommendation_screening_matrix_available"] is False
    assert payload["recommendation_exclusion_payload_available"] is True
    assert payload["source_coverage_basis"] == "dry_run_transient_decision_desk_snapshot"
    command = captured["command"]
    assert isinstance(command, list)
    assert command[command.index("--data-root") + 1] == str(tmp_path / "data")
    assert command[command.index("--output-root") + 1] == str(output_root)
    assert command[command.index("--paper-evidence-operation-root") + 1] == str(paper_operation_root)
    assert command[command.index("--paper-evidence-health-baseline") + 1] == str(paper_health_baseline)
    assert command[command.index("--paper-evidence-status-path") + 1] == str(paper_status_path)
    assert payload["pipeline_actionable_warning_count"] == 3
    assert payload["manual_action_required"] is True
    assert payload["natural_maturity_only"] is False


def test_scheduled_wrapper_marks_only_future_outcomes_as_natural_maturity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    db_path = tmp_path / "data" / "sqlite" / "twstock.db"
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness_path.parent.mkdir(parents=True)
    freshness_path.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    pipeline_summary = {
        "overall_status": "degraded",
        "dry_run": True,
        "confirm": False,
        "warnings_count": 2,
        "warning_counts": {"insufficient_future_data": 2},
        "advisories_count": 1,
        "advisory_counts": {"portfolio_alerts_chip_estimated:2330": 1},
        "errors_count": 0,
        "blocking_gaps": [],
        "source_coverage": {},
    }

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(pipeline_summary),
        ),
    )

    exit_code = run_scheduled_evidence_pipeline_dry_run.main(
        [
            "--dry-run",
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--db-path",
            str(db_path),
        ]
    )

    payload = json.loads(
        (output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json").read_text(
            encoding="utf-8"
        )
    )
    assert exit_code == 0
    assert payload["status"] == "degraded"
    assert payload["pipeline_natural_maturity_warning_count"] == 2
    assert payload["pipeline_natural_maturity_warning_counts"] == {"insufficient_future_data": 2}
    assert payload["pipeline_actionable_warning_count"] == 0
    assert payload["manual_action_required"] is False
    assert payload["natural_maturity_only"] is True
    assert payload["dry_run"] is True
    assert payload["confirm"] is False
    assert payload["writes_evidence_db"] is False
    assert payload["production_scheduler_allowed"] is False


def test_scheduled_wrapper_preserves_ready_with_advisories(tmp_path: Path, monkeypatch) -> None:
    output_root = tmp_path / "output"
    db_path = tmp_path / "data" / "sqlite" / "twstock.db"
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness_path.parent.mkdir(parents=True)
    freshness_path.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    pipeline_summary = {
        "overall_status": "ready_with_advisories",
        "warnings_count": 0,
        "warning_counts": {},
        "advisories_count": 2,
        "advisory_counts": {"portfolio_alerts_chip_estimated:2330": 1},
        "errors_count": 0,
        "blocking_gaps": [],
        "source_coverage": {},
    }

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(pipeline_summary)),
    )

    exit_code = run_scheduled_evidence_pipeline_dry_run.main(
        ["--dry-run", "--data-root", str(tmp_path / "data"), "--output-root", str(output_root), "--db-path", str(db_path)]
    )

    payload = json.loads((output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "ready_with_advisories"
    assert payload["pipeline_advisories_count"] == 2
    assert payload["pipeline_advisory_counts"] == {"portfolio_alerts_chip_estimated:2330": 1}


@pytest.mark.parametrize("host_hour", [5, 10])
def test_scheduled_wrapper_refreshes_paper_health_before_child(tmp_path: Path, monkeypatch, host_hour) -> None:
    output_root = tmp_path / "output"
    db_path = tmp_path / "data" / "sqlite" / "twstock.db"
    paper_operation_root = tmp_path / "paper-operation"
    health_path = output_root / "position_health" / "latest.json"
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness_path.parent.mkdir(parents=True)
    freshness_path.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeHealthRefresh:
        def __init__(self, **kwargs: object) -> None:
            captured["health_init"] = kwargs

        def refresh(self, **kwargs: object) -> dict[str, object]:
            captured["health_refresh"] = kwargs
            health_path.parent.mkdir(parents=True, exist_ok=True)
            health_path.write_text("{}\n", encoding="utf-8")
            return {
                "status": "passed",
                "latest_path": str(health_path),
                "baseline_path": str(health_path),
                "blockers": [],
                "warnings": [],
            }

    monkeypatch.setattr(
        run_scheduled_evidence_pipeline_dry_run,
        "PositionHealthDailyRefreshService",
        FakeHealthRefresh,
    )
    monkeypatch.setattr(
        run_scheduled_evidence_pipeline_dry_run,
        "scheduled_now",
        lambda: datetime(2026, 9, 8, host_hour, 15, tzinfo=ZoneInfo("America/Los_Angeles")),
    )

    pipeline_summary = {
        "overall_status": "ready",
        "warnings_count": 0,
        "warning_counts": {},
        "errors_count": 0,
        "blocking_gaps": [],
        "source_coverage": {},
    }

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = args[0]
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(pipeline_summary))

    monkeypatch.setattr(subprocess, "run", fake_run)
    exit_code = run_scheduled_evidence_pipeline_dry_run.main(
        [
            "--dry-run",
            "--refresh-paper-health",
            "--paper-evidence-operation-root",
            str(paper_operation_root),
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--db-path",
            str(db_path),
        ]
    )

    payload = json.loads(
        (output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json").read_text(
            encoding="utf-8"
        )
    )
    command = captured["command"]
    assert exit_code == 0
    assert isinstance(command, list)
    assert command[command.index("--paper-evidence-health-baseline") + 1] == str(health_path)
    assert payload["paper_health_refresh_status"] == "passed"
    assert payload["paper_evidence_health_baseline"] == str(health_path)
    assert payload["paper_evidence_health_status_path"] == str(
        paper_operation_root / "scheduled" / "paper_portfolio_isolated" / "latest_status.json"
    )
    assert payload["paper_evidence_ledger_db"] == str(
        paper_operation_root / "paper_trade_ledger.sqlite"
    )
    health_init = captured["health_init"]
    assert isinstance(health_init, dict)
    assert str(health_init["coverage_status_path"]) == str(
        paper_operation_root / "scheduled" / "paper_portfolio_isolated" / "latest_status.json"
    )
    assert str(health_init["ledger_db_path"]) == str(
        paper_operation_root / "paper_trade_ledger.sqlite"
    )
    assert payload["manual_action_required"] is False


    health_refresh = captured["health_refresh"]
    assert isinstance(health_refresh, dict)
    expected = datetime(2026,9,8,host_hour,15,tzinfo=ZoneInfo("America/Los_Angeles")).astimezone(ZoneInfo("Asia/Taipei")).date()
    assert health_refresh["as_of_date"] == expected
    assert command[command.index("--decision-date") + 1] == expected.isoformat()

def test_scheduled_wrapper_blocks_stale_health_when_refresh_is_blocked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    db_path = tmp_path / "data" / "sqlite" / "twstock.db"
    paper_operation_root = tmp_path / "paper-operation"
    health_path = output_root / "position_health" / "latest.json"
    health_path.parent.mkdir(parents=True)
    stale_health = json.dumps(
        {"decision_date": "2026-09-07", "positions": [{"stock_code": "2330"}]},
        sort_keys=True,
    ) + "\n"
    health_path.write_text(stale_health, encoding="utf-8")
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness_path.parent.mkdir(parents=True)
    freshness_path.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeHealthRefresh:
        def __init__(self, **kwargs: object) -> None:
            captured["health_init"] = kwargs

        def refresh(self, **kwargs: object) -> dict[str, object]:
            captured["health_refresh"] = kwargs
            return {
                "status": "blocked",
                "latest_path": str(health_path),
                "blockers": ["paper_status_missing"],
                "warnings": [],
            }

    monkeypatch.setattr(
        run_scheduled_evidence_pipeline_dry_run,
        "PositionHealthDailyRefreshService",
        FakeHealthRefresh,
    )
    monkeypatch.setattr(
        run_scheduled_evidence_pipeline_dry_run,
        "scheduled_now",
        lambda: datetime(2026, 9, 8, 5, 15, tzinfo=ZoneInfo("America/Los_Angeles")),
    )

    pipeline_summary = {
        "overall_status": "ready",
        "warnings_count": 0,
        "warning_counts": {},
        "errors_count": 0,
        "blocking_gaps": [],
        "source_coverage": {},
    }

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = args[0]
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(pipeline_summary))

    monkeypatch.setattr(subprocess, "run", fake_run)
    exit_code = run_scheduled_evidence_pipeline_dry_run.main(
        [
            "--dry-run",
            "--refresh-paper-health",
            "--paper-evidence-operation-root",
            str(paper_operation_root),
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--db-path",
            str(db_path),
        ]
    )

    status_path = output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json"
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    command = captured["command"]
    assert isinstance(command, list)
    sentinel = Path(command[command.index("--paper-evidence-health-baseline") + 1])
    assert sentinel != health_path
    assert sentinel.name == ".paper_health_unavailable_20260908.json"
    assert not sentinel.exists()
    assert health_path.read_text(encoding="utf-8") == stale_health
    assert exit_code == 2
    assert payload["status"] == "failed"
    assert payload["exit_code"] == 2
    assert payload["pipeline_exit_code"] == 0
    assert payload["paper_health_refresh_status"] == "blocked"
    assert payload["paper_health_refresh_blocked"] is True
    assert payload["paper_evidence_health_baseline"] == str(sentinel)
    assert payload["manual_action_required"] is True


def test_scheduled_wrapper_connects_market_sources_to_transition_evaluator(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    baseline = tmp_path / "health" / "baseline.json"
    baseline.parent.mkdir(parents=True)
    baseline.write_text(
        json.dumps({"decision_date": "2026-09-08", "positions": []}),
        encoding="utf-8",
    )
    quick = tmp_path / "quick.json"
    freshness = tmp_path / "freshness.json"
    binding = tmp_path / "forward_binding.json"
    quick.write_text("{}", encoding="utf-8")
    freshness.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeMarketSource:
        def __init__(self, **kwargs: object) -> None:
            captured["market_source_init"] = kwargs

        def produce(self, **kwargs: object) -> dict[str, object]:
            captured["market_source_produce"] = kwargs
            return {
                "status": "degraded",
                "condition_source_path": str(tmp_path / "sources" / "condition.json"),
                "metrics_source_path": str(tmp_path / "sources" / "metrics.json"),
                "source_snapshot_hash": "sha256:" + "1" * 64,
                "warnings": ["position_health_source_identity_missing:2330"],
                "blockers": [],
            }

    monkeypatch.setattr(
        run_scheduled_evidence_pipeline_dry_run,
        "PositionHealthMarketSourceProducer",
        FakeMarketSource,
    )
    monkeypatch.setattr(
        run_scheduled_evidence_pipeline_dry_run,
        "scheduled_now",
        lambda: datetime(2026, 9, 8, 5, 15, tzinfo=ZoneInfo("America/Los_Angeles")),
    )

    def fake_evaluate(**kwargs: object) -> dict[str, object]:
        captured["evaluator"] = kwargs
        return {"status": "degraded", "blockers": [], "warnings": ["thesis_missing"]}

    monkeypatch.setattr(
        run_scheduled_evidence_pipeline_dry_run,
        "evaluate_baseline_file",
        fake_evaluate,
    )
    pipeline_summary = {
        "overall_status": "ready",
        "warnings_count": 0,
        "warning_counts": {},
        "errors_count": 0,
        "blocking_gaps": [],
        "source_coverage": {},
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args, returncode=0, stdout=json.dumps(pipeline_summary)
        ),
    )

    exit_code = run_scheduled_evidence_pipeline_dry_run.main(
        [
            "--dry-run",
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--db-path",
            str(tmp_path / "market.sqlite"),
            "--paper-evidence-health-baseline",
            str(baseline),
            "--produce-position-health-sources",
            "--paper-health-source-output",
            str(tmp_path / "sources"),
            "--paper-health-quick-status-path",
            str(quick),
            "--paper-health-freshness-status-path",
            str(freshness),
            "--evaluate-position-health-transition",
            "--paper-health-forward-binding",
            str(binding),
        ]
    )

    payload = json.loads(
        (output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json").read_text(
            encoding="utf-8"
        )
    )
    evaluator = captured["evaluator"]
    assert exit_code == 0
    assert payload["paper_health_source_status"] == "degraded"
    assert payload["paper_health_source_blocked"] is False
    assert payload["paper_health_source_receipt"]["source_snapshot_hash"].startswith("sha256:")
    assert isinstance(evaluator, dict)
    assert evaluator["condition_source_path"] == str(tmp_path / "sources" / "condition.json")
    assert evaluator["metrics_source_path"] == str(tmp_path / "sources" / "metrics.json")
    assert evaluator["forward_binding_path"] == str(binding)
    produce_kwargs = captured["market_source_produce"]
    assert isinstance(produce_kwargs, dict)
    assert produce_kwargs["decision_date"] == "2026-09-08"
    assert "decision_at" not in produce_kwargs
    assert "observed_at" not in produce_kwargs


def test_scheduled_wrapper_runs_daily_forward_binder_for_all_current_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    paper_operation_root = tmp_path / "paper-operation"
    baseline = tmp_path / "health" / "baseline.json"
    baseline.parent.mkdir(parents=True)
    baseline.write_text(
        json.dumps({"source_snapshot_date": "2026-09-09", "positions": []}),
        encoding="utf-8",
    )
    freshness = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness.parent.mkdir(parents=True)
    freshness.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeHealthRefresh:
        def __init__(self, **kwargs: object) -> None:
            pass

        def refresh(self, **kwargs: object) -> dict[str, object]:
            return {"status": "passed", "latest_path": str(baseline)}

    monkeypatch.setattr(
        run_scheduled_evidence_pipeline_dry_run,
        "PositionHealthDailyRefreshService",
        FakeHealthRefresh,
    )
    monkeypatch.setattr(
        run_scheduled_evidence_pipeline_dry_run,
        "scheduled_now",
        lambda: datetime(2026, 9, 9, 5, 15, tzinfo=ZoneInfo("America/Los_Angeles")),
    )

    def fake_bind(**kwargs: object) -> dict[str, object]:
        captured["bind"] = kwargs
        return {
            "status": "degraded",
            "candidate_count": 2,
            "bound_count": 1,
            "awaiting_count": 1,
            "blocked_count": 0,
            "results": [],
            "warnings": ["paper_entry_not_observed"],
            "blockers": [],
        }

    monkeypatch.setattr(
        run_scheduled_evidence_pipeline_dry_run,
        "bind_available_candidates",
        fake_bind,
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(
                {
                    "overall_status": "ready",
                    "warnings_count": 0,
                    "errors_count": 0,
                    "blocking_gaps": [],
                    "source_coverage": {},
                }
            ),
        ),
    )

    exit_code = run_scheduled_evidence_pipeline_dry_run.main(
        [
            "--dry-run",
            "--refresh-paper-health",
            "--bind-forward-thesis",
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--db-path",
            str(tmp_path / "market.sqlite"),
            "--paper-evidence-operation-root",
            str(paper_operation_root),
        ]
    )

    bind_kwargs = captured["bind"]
    assert isinstance(bind_kwargs, dict)
    assert bind_kwargs["baseline_path"] == baseline
    assert bind_kwargs["candidate_root"] == Path.cwd() / "output" / "forward_position_thesis"
    assert bind_kwargs["paper_candidate_root"] == paper_operation_root / "candidates"
    payload = json.loads(
        (output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json").read_text(
            encoding="utf-8"
        )
    )
    assert exit_code == 0
    assert payload["forward_position_thesis_binding"]["bound_count"] == 1
    assert payload["forward_position_thesis_binding_blocked"] is False


@pytest.mark.parametrize(
    ("pacific_now", "child_clock", "decision_date", "exit_as_of_date"),
    [
        (
            datetime(2026, 9, 8, 5, 15, tzinfo=ZoneInfo("America/Los_Angeles")),
            datetime(2026, 9, 8, 12, 15, tzinfo=timezone.utc),
            "2026-09-08",
            "2026-09-08",
        ),
        (
            datetime(2026, 10, 2, 16, 22, tzinfo=ZoneInfo("America/Los_Angeles")),
            datetime(2026, 10, 2, 23, 22, tzinfo=timezone.utc),
            "2026-10-03",
            "2026-10-03",
        ),
    ],
)
def test_scheduled_wrapper_runs_bounded_exit_effectiveness_child(
    tmp_path: Path,
    monkeypatch,
    pacific_now: datetime,
    child_clock: datetime,
    decision_date: str,
    exit_as_of_date: str,
) -> None:
    output_root = tmp_path / "output"
    paper_operation_root = tmp_path / "paper-operation"
    paper_ledger = paper_operation_root / "paper_trade_ledger.sqlite"
    market_db = tmp_path / "market.sqlite"
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness_path.parent.mkdir(parents=True)
    freshness_path.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    monkeypatch.setattr(
        run_scheduled_evidence_pipeline_dry_run,
        "scheduled_now",
        lambda: pacific_now,
    )
    monkeypatch.setattr(
        run_scheduled_evidence_pipeline_dry_run, "_utc_now", lambda: child_clock
    )
    exit_date_key = exit_as_of_date.replace("-", "")
    requested_output_path = output_root / "exit_effectiveness" / f"{exit_date_key}.json"
    requested_output_path.parent.mkdir(parents=True)
    old_payload = _exit_effectiveness_payload(
        generated_at=child_clock - timedelta(seconds=20)
    )
    old_bytes = (_canonical_exit_json(old_payload) + "\n").encode("utf-8")
    requested_output_path.write_bytes(old_bytes)

    calls: list[tuple[list[str], dict[str, object]]] = []
    pipeline_summary = {
        "overall_status": "ready",
        "warnings_count": 0,
        "errors_count": 0,
        "blocking_gaps": [],
        "source_coverage": {},
    }
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        command = list(args[0])
        calls.append((command, dict(kwargs)))
        if any(str(item).endswith("run_exit_effectiveness_daily.py") for item in command):
            output_path = Path(command[command.index("--output") + 1])
            exit_receipt = _fake_exit_effectiveness_stdout(
                output_path=output_path,
                generated_at=child_clock + timedelta(seconds=1),
            )
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=json.dumps(exit_receipt),
            )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps(pipeline_summary),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    exit_code = run_scheduled_evidence_pipeline_dry_run.main(
        [
            "--dry-run",
            "--run-exit-effectiveness",
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--db-path",
            str(market_db),
            "--paper-evidence-operation-root",
            str(paper_operation_root),
            "--paper-evidence-ledger-db",
            str(paper_ledger),
        ]
    )

    status_path = output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json"
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["exit_effectiveness_status"] == "passed"
    assert payload["exit_effectiveness_blocked"] is False
    assert payload["exit_effectiveness_receipt"]["receipt"]["research_only"] is True
    assert payload["exit_effectiveness_receipt"]["receipt"]["historical_backfill"] is False
    assert payload["exit_effectiveness_artifact_identity_status"] == "verified"
    assert payload["decision_date"] == decision_date
    assert payload["exit_effectiveness_requested_as_of_date"] == exit_as_of_date
    assert payload["exit_effectiveness_as_of_date"] == exit_as_of_date
    assert payload["exit_effectiveness_date_role"] == (
        "same_analysis_day"
        if exit_as_of_date == decision_date
        else "current_outcome_sidecar"
    )
    assert payload["exit_effectiveness_receipt"]["producer_receipt"]["generated_at"] == (
        (child_clock + timedelta(seconds=1)).isoformat()
    )
    actual_artifact = Path(payload["exit_effectiveness_artifact_path"])
    assert actual_artifact.parent == requested_output_path.parent
    assert actual_artifact.name.startswith(f"{exit_date_key}_")
    assert payload["exit_effectiveness_receipt"]["artifact_path"] == str(actual_artifact)
    assert payload["exit_effectiveness_receipt"]["receipt"]["artifact_path"] == str(
        actual_artifact
    )
    assert payload["exit_effectiveness_receipt"]["producer_receipt"]["artifact_path"] == str(
        actual_artifact
    )
    assert payload["exit_effectiveness_output"] == str(requested_output_path)
    assert payload["exit_effectiveness_requested_output"] == str(requested_output_path)
    assert requested_output_path.read_bytes() == old_bytes
    assert actual_artifact.read_bytes() != old_bytes
    assert len(calls) == 2
    exit_command, exit_kwargs = calls[0]
    assert "scripts/run_exit_effectiveness_daily.py" in exit_command
    assert "--as-of-date" not in exit_command
    assert exit_command[exit_command.index("--transition-db") + 1] == str(
        output_root / "position_health_transition" / "position_health_transitions_v2.sqlite"
    )
    assert exit_command[exit_command.index("--paper-ledger-db") + 1] == str(paper_ledger)
    assert exit_command[exit_command.index("--market-db") + 1] == str(market_db)
    assert exit_command[exit_command.index("--output") + 1] == str(
        requested_output_path
    )
    assert exit_kwargs["timeout"] == 300
    assert exit_kwargs["cwd"] == str(run_scheduled_evidence_pipeline_dry_run.REPO_ROOT)
    assert Path(payload["exit_effectiveness_log"]).is_file()


def test_exit_effectiveness_verifies_initial_requested_artifact_path(tmp_path: Path) -> None:
    runner = run_scheduled_evidence_pipeline_dry_run
    child_started_at = datetime(2026, 9, 8, 12, 15, tzinfo=timezone.utc)
    child_completed_at = child_started_at + timedelta(seconds=2)
    requested_path = tmp_path / "output" / "exit_effectiveness" / "20260908.json"
    receipt = _fake_exit_effectiveness_stdout(
        output_path=requested_path,
        generated_at=child_started_at + timedelta(seconds=1),
    )

    actual_path, file_hash = runner._verify_exit_effectiveness_artifact(
        receipt=receipt,
        requested_output_path=requested_path,
        child_started_at=child_started_at,
        child_completed_at=child_completed_at,
    )

    assert actual_path == requested_path.resolve()
    assert file_hash == receipt["artifact_file_sha256"]
    assert runner.EXIT_EFFECTIVENESS_ARTIFACT_MAX_BYTES == 32 * 1024 * 1024


def test_exit_effectiveness_verifier_binds_taipei_date_not_pacific_or_utc(
    tmp_path: Path,
) -> None:
    runner = run_scheduled_evidence_pipeline_dry_run
    child_started_at = datetime(2026, 10, 2, 23, 22, tzinfo=timezone.utc)
    child_completed_at = child_started_at + timedelta(seconds=2)
    assert child_started_at.astimezone(
        ZoneInfo("America/Los_Angeles")
    ).date().isoformat() == "2026-10-02"
    requested_path = tmp_path / "output" / "exit_effectiveness" / "20261003.json"
    receipt = _fake_exit_effectiveness_stdout(
        output_path=requested_path,
        generated_at=child_started_at + timedelta(seconds=1),
    )
    assert receipt["generated_at"] == "2026-10-02T23:22:01+00:00"
    assert receipt["as_of_date"] == "2026-10-03"

    actual_path, file_hash = runner._verify_exit_effectiveness_artifact(
        receipt=receipt,
        requested_output_path=requested_path,
        child_started_at=child_started_at,
        child_completed_at=child_completed_at,
    )

    assert actual_path == requested_path.resolve()
    assert file_hash == receipt["artifact_file_sha256"]
    with pytest.raises(ValueError, match="as_of_date_mismatch"):
        runner._verify_exit_effectiveness_artifact(
            receipt=receipt,
            requested_output_path=requested_path.with_name("20261002.json"),
            child_started_at=child_started_at,
            child_completed_at=child_completed_at,
        )
    utc_or_pacific_day_receipt = dict(receipt)
    utc_or_pacific_day_receipt["as_of_date"] = "2026-10-02"
    with pytest.raises(ValueError, match="as_of_date_mismatch"):
        runner._verify_exit_effectiveness_artifact(
            receipt=utc_or_pacific_day_receipt,
            requested_output_path=requested_path,
            child_started_at=child_started_at,
            child_completed_at=child_completed_at,
        )


def test_exit_effectiveness_v1_missing_path_blocks_without_stale_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    runner = run_scheduled_evidence_pipeline_dry_run
    child_clock = datetime(2026, 9, 8, 12, 15, tzinfo=timezone.utc)
    requested_path = tmp_path / "output" / "exit_effectiveness" / "20260908.json"
    requested_path.parent.mkdir(parents=True)
    old_bytes = b'{"old":"immutable artifact"}\n'
    requested_path.write_bytes(old_bytes)
    child_stdout = _fake_exit_effectiveness_stdout(
        output_path=requested_path,
        generated_at=child_clock + timedelta(seconds=1),
    )
    child_stdout.pop("artifact_path")
    monkeypatch.setattr(runner, "_utc_now", lambda: child_clock)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout=json.dumps(child_stdout)
        ),
    )

    result = runner._run_exit_effectiveness_child(
        transition_db=tmp_path / "transition.sqlite",
        paper_ledger_db=tmp_path / "ledger.sqlite",
        market_db=tmp_path / "market.sqlite",
        calendar_cache=tmp_path / "calendar",
        temporary_closure_cache=None,
        output_path=requested_path,
        log_path=tmp_path / "child.log",
    )

    assert result["blocked"] is True
    assert result["status"] == "blocked"
    assert result["artifact_identity_status"] == "invalid"
    assert result["artifact_path"] is None
    assert result["actual_artifact_path"] is None
    assert result["receipt"]["artifact_path"] is None
    assert result["requested_artifact_path"] == str(requested_path)
    assert any("artifact_path_missing" in item for item in result["blockers"])
    assert requested_path.read_bytes() == old_bytes


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("schema", "schema_version_invalid"),
        ("date", "as_of_date_mismatch"),
        ("clock", "generated_at_outside_child_run"),
        ("naive_clock", "generated_at_naive"),
        ("formal_flag", "formal_credit_invalid"),
        ("hash_format", "artifact_file_sha256_invalid"),
        ("missing_path", "artifact_path_missing"),
        ("outside_root", "artifact_path_outside_root"),
        ("bad_suffix", "artifact_suffix_mismatch"),
        ("stdout_body", "artifact_body_stdout_mismatch"),
        ("evidence_hash", "evidence_hash_mismatch"),
        ("file_tamper", "artifact_file_sha256_mismatch"),
    ],
)
def test_exit_effectiveness_artifact_identity_mismatch_fails_closed(
    tmp_path: Path, mutation: str, expected_reason: str
) -> None:
    runner = run_scheduled_evidence_pipeline_dry_run
    child_started_at = datetime(2026, 9, 8, 12, 15, tzinfo=timezone.utc)
    child_completed_at = child_started_at + timedelta(seconds=2)
    requested_path = tmp_path / "output" / "exit_effectiveness" / "20260908.json"
    receipt = _fake_exit_effectiveness_stdout(
        output_path=requested_path,
        generated_at=child_started_at + timedelta(seconds=1),
    )
    if mutation == "schema":
        receipt["schema_version"] = "unknown.v1"
    elif mutation == "date":
        receipt["as_of_date"] = "2026-09-07"
    elif mutation == "clock":
        receipt["generated_at"] = "2026-09-08T11:00:00+00:00"
    elif mutation == "naive_clock":
        receipt["generated_at"] = "2026-09-08T12:15:01"
    elif mutation == "formal_flag":
        receipt["formal_credit"] = True
    elif mutation == "hash_format":
        receipt["artifact_file_sha256"] = "not-a-sha"
    elif mutation == "missing_path":
        receipt.pop("artifact_path")
    elif mutation == "outside_root":
        receipt["artifact_path"] = str(tmp_path / "outside.json")
    elif mutation == "bad_suffix":
        receipt["artifact_path"] = str(
            requested_path.with_name("20260908_0000000000000000.json").resolve()
        )
    elif mutation == "stdout_body":
        receipt["status"] = "degraded"
    elif mutation == "evidence_hash":
        artifact_path = Path(receipt["artifact_path"])
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        payload["evidence_hash"] = "sha256:" + "f" * 64
        encoded = (_canonical_exit_json(payload) + "\n").encode("utf-8")
        artifact_path.write_bytes(encoded)
        receipt["evidence_hash"] = payload["evidence_hash"]
        receipt["artifact_file_sha256"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    elif mutation == "file_tamper":
        requested_path.write_bytes(requested_path.read_bytes() + b" ")

    with pytest.raises(ValueError, match=expected_reason):
        runner._verify_exit_effectiveness_artifact(
            receipt=receipt,
            requested_output_path=requested_path,
            child_started_at=child_started_at,
            child_completed_at=child_completed_at,
        )


def test_exit_effectiveness_artifact_verification_rejects_symlink(
    tmp_path: Path,
) -> None:
    runner = run_scheduled_evidence_pipeline_dry_run
    child_started_at = datetime(2026, 9, 8, 12, 15, tzinfo=timezone.utc)
    child_completed_at = child_started_at + timedelta(seconds=2)
    requested_path = tmp_path / "output" / "exit_effectiveness" / "20260908.json"
    receipt = _fake_exit_effectiveness_stdout(
        output_path=requested_path,
        generated_at=child_started_at + timedelta(seconds=1),
    )
    outside = tmp_path / "outside.json"
    outside.write_bytes(requested_path.read_bytes())
    requested_path.unlink()
    try:
        requested_path.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"filesystem does not permit symlink setup: {exc}")
    with pytest.raises(Exception, match="no-follow|reparse|regular file|legacy"):
        runner._verify_exit_effectiveness_artifact(
            receipt=receipt,
            requested_output_path=requested_path,
            child_started_at=child_started_at,
            child_completed_at=child_completed_at,
        )


def test_exit_effectiveness_artifact_verification_enforces_size_bound(
    tmp_path: Path, monkeypatch
) -> None:
    runner = run_scheduled_evidence_pipeline_dry_run
    child_started_at = datetime(2026, 9, 8, 12, 15, tzinfo=timezone.utc)
    child_completed_at = child_started_at + timedelta(seconds=2)
    requested_path = tmp_path / "output" / "exit_effectiveness" / "20260908.json"
    receipt = _fake_exit_effectiveness_stdout(
        output_path=requested_path,
        generated_at=child_started_at + timedelta(seconds=1),
    )
    # Exercise the cap without allocating a 32 MiB fixture; assert the fixed
    # production value separately so this remains an Exit-only contract.
    assert runner.EXIT_EFFECTIVENESS_ARTIFACT_MAX_BYTES == 32 * 1024 * 1024
    monkeypatch.setattr(runner, "EXIT_EFFECTIVENESS_ARTIFACT_MAX_BYTES", 64)
    with pytest.raises(Exception):
        runner._verify_exit_effectiveness_artifact(
            receipt=receipt,
            requested_output_path=requested_path,
            child_started_at=child_started_at,
            child_completed_at=child_completed_at,
        )


def test_scheduled_wrapper_surfaces_exit_effectiveness_timeout_without_stale_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness_path.parent.mkdir(parents=True)
    freshness_path.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    pipeline_summary = {
        "overall_status": "ready",
        "warnings_count": 0,
        "errors_count": 0,
        "blocking_gaps": [],
        "source_coverage": {},
    }

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        command = list(args[0])
        if any(str(item).endswith("run_exit_effectiveness_daily.py") for item in command):
            raise subprocess.TimeoutExpired(
                cmd=command,
                timeout=run_scheduled_evidence_pipeline_dry_run.EXIT_EFFECTIVENESS_TIMEOUT_SECONDS,
                output="partial child output",
            )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps(pipeline_summary),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    exit_code = run_scheduled_evidence_pipeline_dry_run.main(
        [
            "--dry-run",
            "--run-exit-effectiveness",
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--db-path",
            str(tmp_path / "market.sqlite"),
        ]
    )

    status_path = output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json"
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert payload["status"] == "failed"
    assert payload["exit_effectiveness_status"] == "blocked"
    assert payload["exit_effectiveness_blocked"] is True
    assert "exit_effectiveness_child_timeout" in payload["exit_effectiveness_receipt"]["blockers"]
    assert not (output_root / "exit_effectiveness" / "20260908.json").exists()
    assert "partial child output" in Path(payload["exit_effectiveness_log"]).read_text(
        encoding="utf-8"
    )


def test_controlled_validation_health_artifacts_are_separate_from_canonical(tmp_path, monkeypatch):
    runner=run_scheduled_evidence_pipeline_dry_run
    now,_status,_payload,_reader=_binding_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(runner,"scheduled_now",lambda:now)
    captured={}
    class Refresh:
        def __init__(self,**kwargs):pass
        def refresh(self,**kwargs):
            captured["health"]=kwargs
            p=Path(kwargs["output_dir"])/"latest.json";p.parent.mkdir(parents=True);p.write_text("{}",encoding="utf-8")
            return {"status":"passed","latest_path":str(p),"blockers":[],"warnings":[]}
    class Market:
        def __init__(self,**kwargs):captured["market_init"]=kwargs
        def produce(self,**kwargs):
            captured["market"]=kwargs
            return {"status":"degraded","blockers":[],"warnings":[]}
    def evaluate(**kwargs):
        captured["transition"]=kwargs
        return {"status":"degraded","blockers":[],"warnings":[]}
    monkeypatch.setattr(runner,"PositionHealthDailyRefreshService",Refresh)
    monkeypatch.setattr(runner,"PositionHealthMarketSourceProducer",Market)
    monkeypatch.setattr(runner,"evaluate_baseline_file",evaluate)
    monkeypatch.setattr(subprocess,"run",lambda *args,**kwargs:subprocess.CompletedProcess(args=args,returncode=0,stdout=json.dumps({"overall_status":"degraded","warnings_count":0,"warning_counts":{},"errors_count":0,"blocking_gaps":[],"source_coverage":{}})))
    canonical=tmp_path
    qa=tmp_path/"qa";status=qa/"validation.json"
    runner.main(["--data-root",str(tmp_path/"data"),"--output-root",str(canonical),"--db-path",str(tmp_path/"market.sqlite"),"--dry-run","--bind-scheduled-recommendation","--validation-decision-date","2026-09-29","--status-path",str(status),"--refresh-paper-health","--produce-position-health-sources","--evaluate-position-health-transition"])
    for item in [captured["health"],captured["market"],captured["transition"]]:
        assert Path(item["output_dir"]).is_relative_to(qa/"controlled_runs")
    assert not (canonical/"position_health_transition").exists()
    assert captured["health"]["as_of_date"].isoformat()=="2026-09-29"
