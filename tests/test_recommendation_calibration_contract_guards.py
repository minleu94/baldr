from __future__ import annotations

from io import StringIO
from datetime import datetime, timezone
import gc
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
from typing import Any
from zoneinfo import ZoneInfo

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
from tests.test_recommendation_calibration_source_contract import (
    _daily_capture,
    _publish_technical,
    _source_db,
)
from data_module.recommendation_calibration_source_contract import (
    build_technical_computation_evidence,
    capture_technical_input_snapshot,
    publish_technical_indicator_receipt,
    reuse_verified_technical_computation_receipt,
)
from data_module.official_daily_price_custody import (
    persist_official_daily_price_response,
)


def _formal_quick_fixture(
    tmp_path: Path,
    *,
    available_at: str = "2026-09-20T04:30:44.151755-07:00",
    source_date_start: str = "2026-09-15",
    source_date_end: str = "2026-09-18",
) -> tuple[Path, Path, Path, datetime]:
    data_root = (tmp_path / "formal-data").resolve()
    formal_output_root = data_root / "output"
    source_db = (data_root / "sqlite" / "twstock.db").resolve()
    receipt_path = (
        formal_output_root
        / "scheduled"
        / "technical_indicator_publication"
        / source_date_end
        / "fixture-receipt"
        / "receipt.json"
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": "technical-indicator-publication-receipt.v1",
                "source_date_start": source_date_start,
                "source_date_end": source_date_end,
                "available_at": available_at,
                "technical_step_status": "skipped",
                "technical_output": {
                    "source_db": str(source_db),
                    "actual_date_start": source_date_start,
                    "actual_date_end": source_date_end,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    status_path = formal_output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(
            {
                "status": "passed_with_warnings",
                "run_id": "fixture-20260920",
                "data_root": str(data_root),
                "output_root": str(formal_output_root),
                "formal_output_root": str(formal_output_root),
                "authorized_technical_output_roots": [str(formal_output_root)],
                "technical_publication_receipt": {
                    "status": "published",
                    "receipt_path": str(receipt_path),
                    "available_at": available_at,
                    "source_date_start": source_date_start,
                    "source_date_end": source_date_end,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    now = datetime(2026, 9, 20, 5, 45, tzinfo=ZoneInfo("America/Los_Angeles"))
    return data_root, source_db, receipt_path, now


def _capture_daily_price(
    output_root: Path,
    *,
    source_date: str,
    captured_at: datetime,
    symbols: tuple[str, ...] = ("1101", "2330"),
) -> dict[str, object]:
    raw = json.dumps(
        {
            "tables": [
                {
                    "fields": ["證券代號", "收盤價"],
                    "data": [[symbol, "100"] for symbol in symbols],
                }
            ]
        },
        ensure_ascii=False,
    ).encode("utf-8")
    return persist_official_daily_price_response(
        output_root=output_root,
        venue="twse",
        source_id="twse.mi_index.daily_price",
        source_date=source_date,
        requested_url="https://www.twse.com.tw/exchangeReport/MI_INDEX",
        final_url="https://www.twse.com.tw/exchangeReport/MI_INDEX",
        request_parameters={"response": "json", "date": source_date.replace("-", "")},
        http_status=200,
        response_headers={"Content-Type": "application/json"},
        raw_response=raw,
        captured_at=captured_at,
        row_count=len(symbols),
        source_columns=("證券代號", "收盤價"),
        parser_id="pipeline-routing-fixture.v1",
    )


def _multi_day_verified_publication(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    """建立供 pipeline.main 使用的真實同日多日 computation witness。"""

    data_root = (tmp_path / "formal-data").resolve()
    output_root = data_root / "output"
    source_db = (data_root / "sqlite" / "twstock.db").resolve()
    source_db.parent.mkdir(parents=True, exist_ok=True)
    _source_db(source_db)
    with sqlite3.connect(source_db) as connection:
        for source_date in ("2026-09-12", "2026-09-13"):
            for symbol in ("1101", "2330"):
                connection.execute(
                    'INSERT INTO daily_prices VALUES (?, ?, ?)',
                    (source_date, symbol, 100.0),
                )
                connection.execute(
                    'INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?)',
                    (source_date, symbol, "55", "1.5", "20"),
                )
        connection.commit()

    receipts = [
        _capture_daily_price(
            output_root,
            source_date=source_date,
            captured_at=datetime.fromisoformat(source_date + "T05:00:00+00:00"),
        )
        for source_date in ("2026-09-12", "2026-09-13", "2026-09-14")
    ]
    computation = build_technical_computation_evidence(
        source_db=source_db,
        calculation_result={"success": True, "updated_stocks": ["1101", "2330"]},
        source_date_start="2026-09-12",
        source_date_end="2026-09-14",
        started_at="2026-09-14T05:00:00+00:00",
        completed_at="2026-09-14T05:05:00+00:00",
        input_snapshot=capture_technical_input_snapshot(
            source_db,
            source_date_start="2026-09-12",
            source_date_end="2026-09-14",
        ),
    )
    publication = publish_technical_indicator_receipt(
        output_root=output_root,
        source_db=source_db,
        update_status={
            "status": "passed",
            "run_id": "pipeline-routing-multi-day",
            "start_date": "2026-09-12",
            "end_date": "2026-09-14",
            "completed_at": "2026-09-14T05:05:00+00:00",
            "steps": [
                {
                    "name": "calculate_technical_indicators",
                    "status": "passed",
                    "result": {
                        "success": True,
                        "source_custody": receipts[0],
                        "technical_computation": computation,
                    },
                }
            ],
        },
    )
    assert publication["status"] == "published"
    return data_root, source_db, publication


def _write_formal_quick_pointer(
    data_root: Path,
    publication: dict[str, object],
) -> None:
    output_root = (data_root / "output").resolve()
    status_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "run_id": "pipeline-routing-pointer",
                "data_root": str(data_root),
                "output_root": str(output_root),
                "formal_output_root": str(output_root),
                "authorized_technical_output_roots": [str(output_root)],
                "technical_publication_receipt": {
                    "status": "published",
                    "receipt_path": publication["receipt_path"],
                    "available_at": publication["available_at"],
                    "source_date_start": publication["source_date_start"],
                    "source_date_end": publication["source_date_end"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _patch_pipeline_now(monkeypatch, now: datetime) -> None:
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz is not None else now.replace(tzinfo=None)

    monkeypatch.setattr(pipeline, "datetime", FixedDateTime)


def _fake_pipeline_child(calls: list[dict[str, Any]]):
    def fake_run_child(**kwargs):
        name = str(kwargs["name"])
        environment = dict(kwargs["environment"])
        arguments = list(kwargs["arguments"])
        calls.append(
            {
                "name": name,
                "script": kwargs["script"],
                "arguments": arguments,
                "environment": environment,
            }
        )
        child_root = Path(environment["RECOMMENDATION_LEARNING_OUTPUT_ROOT"])
        status_path = pipeline._status_path(child_root, name)
        child_status: dict[str, object] = {
            "status": "passed",
            "warnings": [],
            "blockers": [],
        }
        if name == "recommendation_snapshot":
            child_status["result_id"] = "synthetic-snapshot-result"
            child_status["decision_date"] = pipeline.datetime.now(pipeline.TAIPEI).date().isoformat()
            child_status["snapshot_cohort"] = {
                "schema_version": "scheduled-recommendation-snapshot-cohort.v1",
                "requested_symbols": ["1101"],
                "eligible_symbols": ["1101"],
                "missing_symbols": [],
                "degraded_symbols": [],
                "excluded_symbols": [],
                "cohort_hash": "sha256:" + "a" * 64,
            }
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(
            json.dumps(child_status, ensure_ascii=False),
            encoding="utf-8",
        )
        stdout_bytes = b""
        artifact_metadata: dict[str, object] = {}
        if name == "recommendation_snapshot":
            # 模擬另一個同日 invocation 在 parent handoff 前覆寫 latest；
            # pipeline 必須仍採用本次 _run_child 回傳的 child_status。
            status_path.write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "result_id": "stale-other-run-result",
                        "decision_date": child_status["decision_date"],
                        "snapshot_cohort": {
                            "eligible_symbols": ["2330"],
                            "cohort_hash": "sha256:" + "b" * 64,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stdout_bytes = json.dumps(child_status, ensure_ascii=False).encode("utf-8")
            artifact_path = kwargs.get("snapshot_stdout_artifact_path")
            runs_root = kwargs.get("snapshot_stdout_runs_root")
            if artifact_path is not None and runs_root is not None:
                artifact_path, artifact_size, artifact_hash = (
                    pipeline._write_snapshot_invocation_stdout_artifact(
                        path=artifact_path,
                        allowed_runs_root=runs_root,
                        raw_stdout=stdout_bytes,
                    )
                )
                artifact_metadata = {
                    "child_stdout_artifact_path": artifact_path,
                    "child_stdout_artifact_size": artifact_size,
                    "child_stdout_sha256": artifact_hash,
                }
                calls[-1].update(artifact_metadata)
        return {
            "name": name,
            "script": kwargs["script"],
            "command": [],
            "returncode": 0,
            "status": "passed",
            "status_path": str(status_path),
            "child_status": child_status,
            "child_status_source": "invocation_stdout_json",
            **artifact_metadata,
            "child_warnings": [],
            "child_blockers": [],
            "stdout_stderr_tail": "",
            "timeout_seconds": kwargs.get("timeout_seconds"),
            "recoverable": False,
        }

    return fake_run_child


def _snapshot_child_stdout_payload(
    *,
    result_id: str = "snapshot-invocation-result",
    cohort_hash: str = "sha256:" + "a" * 64,
) -> bytes:
    return json.dumps(
        {
            "task": "baldr-recommendation-snapshot-daily",
            "status": "passed",
            "decision_date": "2026-09-25",
            "result_id": result_id,
            "snapshot_cohort": {
                "schema_version": "scheduled-recommendation-snapshot-cohort.v1",
                "eligible_symbols": ["1101"],
                "cohort_hash": cohort_hash,
            },
        },
        ensure_ascii=True,
        indent=2,
    ).encode("utf-8")


def test_snapshot_child_parser_uses_one_typed_stdout_object_and_rejects_ambiguity() -> None:
    payload_bytes = _snapshot_child_stdout_payload()
    payload, error = pipeline._snapshot_child_payload_from_stdout(
        b"logger: starting {not-json}\n" + payload_bytes + b"\ntrailing diagnostic\n"
    )
    assert error is None
    assert payload is not None
    assert payload["result_id"] == "snapshot-invocation-result"

    ambiguous, error = pipeline._snapshot_child_payload_from_stdout(
        payload_bytes + b"\n" + payload_bytes
    )
    assert ambiguous is None
    assert error == "snapshot_child_stdout_receipt_missing_or_ambiguous"

    unsupported = _snapshot_child_stdout_payload().replace(
        b"scheduled-recommendation-snapshot-cohort.v1",
        b"unknown-cohort-schema.v1",
    )
    rejected, error = pipeline._snapshot_child_payload_from_stdout(unsupported)
    assert rejected is None
    assert error == "snapshot_child_stdout_cohort_schema_unsupported"


@pytest.mark.parametrize(
    ("stdout", "expected_status", "expected_blocker"),
    (
        (_snapshot_child_stdout_payload(), "passed", None),
        (b"malformed snapshot child output", "failed", "snapshot_child_stdout_receipt_missing_or_ambiguous"),
    ),
)
def test_snapshot_child_run_uses_invocation_stdout_not_shared_latest_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stdout: bytes,
    expected_status: str,
    expected_blocker: str | None,
) -> None:
    output_root = tmp_path / "output"
    runs_root = (
        output_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "runs"
    )
    invocation_dir = runs_root / "invocation"
    invocation_dir.mkdir(parents=True)
    stdout_artifact_path = invocation_dir / pipeline._SNAPSHOT_INVOCATION_STDOUT_NAME
    stale_status_path = pipeline._status_path(output_root, "recommendation_snapshot")
    stale_status_path.parent.mkdir(parents=True, exist_ok=True)
    stale_status_path.write_text(
        json.dumps(
            {
                "task": "baldr-recommendation-snapshot-daily",
                "status": "passed",
                "decision_date": "2026-09-25",
                "result_id": "stale-other-invocation",
                "snapshot_cohort": {
                    "schema_version": "scheduled-recommendation-snapshot-cohort.v1",
                    "eligible_symbols": ["2330"],
                    "cohort_hash": "sha256:" + "b" * 64,
                },
            }
        ),
        encoding="utf-8",
    )

    def run(_command, **kwargs):
        assert kwargs["text"] is False
        return subprocess.CompletedProcess(_command, 0, stdout, b"")

    monkeypatch.setattr(pipeline.subprocess, "run", run)
    result = pipeline._run_child(
        name="recommendation_snapshot",
        script="scripts/scheduled/run_scheduled_recommendation_snapshot.py",
        arguments=[],
        environment={"RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(output_root)},
        log_handle=StringIO(),
        timeout_seconds=1,
        snapshot_stdout_artifact_path=stdout_artifact_path,
        snapshot_stdout_runs_root=runs_root,
    )

    if expected_blocker is None:
        assert result["status"] == expected_status
        assert result["child_status_source"] == "invocation_stdout_json"
        assert result["child_status"]["result_id"] == "snapshot-invocation-result"
        assert result["child_status"]["snapshot_cohort"]["eligible_symbols"] == ["1101"]
        assert result["child_stdout_sha256"] == "sha256:" + hashlib.sha256(stdout).hexdigest()
        assert result["child_stdout_artifact_path"] == str(stdout_artifact_path.resolve())
    else:
        assert result["status"] == expected_status
        assert result["child_status"] is None
        assert expected_blocker in result["child_blockers"]


def test_snapshot_child_run_fails_closed_without_invocation_stdout_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"

    def run(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            _snapshot_child_stdout_payload(),
            b"",
        )

    monkeypatch.setattr(pipeline.subprocess, "run", run)
    result = pipeline._run_child(
        name="recommendation_snapshot",
        script="scripts/scheduled/run_scheduled_recommendation_snapshot.py",
        arguments=[],
        environment={"RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(output_root)},
        log_handle=StringIO(),
        timeout_seconds=1,
    )

    assert result["status"] == "failed"
    assert result["child_status"]["result_id"] == "snapshot-invocation-result"
    assert result["child_stdout_artifact_path"] is None
    assert "snapshot_child_stdout_artifact_path_missing" in result["child_blockers"]


def _availability_contract(*, event_available_at: str) -> tuple[dict[str, Any], dict[str, Any]]:
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


def test_technical_child_plan_uses_formal_receipt_window_and_root(tmp_path: Path) -> None:
    data_root, source_db, receipt_path, _now = _formal_quick_fixture(tmp_path)

    plan = pipeline._technical_child_plan(
        data_root=data_root,
        source_db=source_db,
        source_date_start="2026-09-20",
        source_date_end="2026-09-20",
    )

    assert plan["status"] == "ready"
    assert plan["formal_output_root"] == str(data_root / "output")
    assert plan["status_path"] == str(
        data_root / "output" / "scheduled" / "data_update_quick" / "latest_status.json"
    )
    assert plan["source_date_start"] == "2026-09-20"
    assert plan["source_date_end"] == "2026-09-20"
    hint = pipeline._formal_receipt_window_hint(
        data_root=data_root,
        source_db=source_db,
    )
    assert hint["status"] == "ready"
    assert hint["receipt_path"] == str(receipt_path.resolve())
    assert hint["source_date_start"] == "2026-09-15"
    assert hint["source_date_end"] == "2026-09-18"


def test_technical_window_hint_rejects_stale_and_future_windows(tmp_path: Path) -> None:
    stale_root, stale_db, _receipt, now = _formal_quick_fixture(tmp_path / "stale")
    stale_hint = pipeline._formal_receipt_window_hint(
        data_root=stale_root,
        source_db=stale_db,
    )
    assert not pipeline._technical_window_matches_decision(
        stale_hint,
        decision_date="2026-09-21",
        now=datetime(2026, 9, 21, 5, 45, tzinfo=ZoneInfo("America/Los_Angeles")),
    )

    future_root, future_db, _receipt, _ = _formal_quick_fixture(
        tmp_path / "future",
        available_at="2026-09-22T04:30:44.151755-07:00",
        source_date_start="2026-09-22",
        source_date_end="2026-09-22",
    )
    future_hint = pipeline._formal_receipt_window_hint(
        data_root=future_root,
        source_db=future_db,
    )
    assert not pipeline._technical_window_matches_decision(
        future_hint,
        decision_date="2026-09-21",
        now=now,
    )


def test_technical_child_plan_blocks_custom_source_db_before_status_read(
    monkeypatch, tmp_path: Path
) -> None:
    data_root = (tmp_path / "formal-data").resolve()
    custom_db = (tmp_path / "custom.sqlite").resolve()
    monkeypatch.setattr(
        pipeline,
        "_read_json",
        lambda path: pytest.fail(f"status must not be read: {path}"),
    )
    plan = pipeline._technical_child_plan(
        data_root=data_root,
        source_db=custom_db,
        source_date_start="2026-09-20",
        source_date_end="2026-09-20",
    )

    assert plan["status"] == "blocked"
    assert plan["reason"] == "technical_source_db_mismatch"


def test_normal_refresh_keeps_decision_date_when_formal_receipt_is_missing(
    tmp_path: Path,
) -> None:
    data_root = (tmp_path / "formal-data").resolve()
    source_db = (data_root / "sqlite" / "twstock.db").resolve()
    plan = pipeline._technical_child_plan(
        data_root=data_root,
        source_db=source_db,
        source_date_start="2026-09-20",
        source_date_end="2026-09-20",
    )
    hint = pipeline._formal_receipt_window_hint(
        data_root=data_root,
        source_db=source_db,
    )

    assert plan["status"] == "ready"
    assert hint["status"] == "unavailable"
    assert plan["source_date_start"] == "2026-09-20"
    assert plan["source_date_end"] == "2026-09-20"


def test_technical_child_invocation_is_formal_and_preserves_shadow_environment(
    tmp_path: Path,
) -> None:
    data_root, source_db, _receipt_path, _now = _formal_quick_fixture(tmp_path)
    plan = pipeline._technical_child_plan(
        data_root=data_root,
        source_db=source_db,
        source_date_start="2026-09-20",
        source_date_end="2026-09-20",
    )
    hint = pipeline._formal_receipt_window_hint(
        data_root=data_root,
        source_db=source_db,
    )
    plan.update(
        {
            "source_date_start": hint["source_date_start"],
            "source_date_end": hint["source_date_end"],
            "receipt_path": hint["receipt_path"],
        }
    )
    shadow_root = (tmp_path / "shadow").resolve()
    base_environment = {
        "OUTPUT_ROOT": str(shadow_root),
        "RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(shadow_root),
        "DB_PATH": str(source_db),
    }

    arguments, child_environment = pipeline._technical_child_invocation(
        data_root=data_root,
        plan=plan,
        base_environment=base_environment,
        window_weekdays=10,
        daily_delay_seconds=0.5,
        tpex_delay_seconds=0.5,
        broker_delay_seconds=0.5,
    )

    assert arguments[arguments.index("--output-root") + 1] == str(data_root / "output")
    assert arguments[arguments.index("--formal-output-root") + 1] == str(data_root / "output")
    assert arguments[arguments.index("--start-date") + 1] == "2026-09-15"
    assert arguments[arguments.index("--end-date") + 1] == "2026-09-18"
    assert arguments[arguments.index("--status-path") + 1] == plan["status_path"]
    assert "--calendar-cache-path" not in arguments
    assert "--temporary-closure-path" not in arguments
    assert "--skip-candidate-update" not in arguments
    assert child_environment["OUTPUT_ROOT"] == str(data_root / "output")
    assert child_environment["RECOMMENDATION_LEARNING_OUTPUT_ROOT"] == str(data_root / "output")
    assert child_environment["DB_PATH"] == str(source_db)
    assert base_environment["OUTPUT_ROOT"] == str(shadow_root)
    assert base_environment["RECOMMENDATION_LEARNING_OUTPUT_ROOT"] == str(shadow_root)


def test_technical_child_invocation_forwards_calendar_and_candidate_skip_options(
    tmp_path: Path,
) -> None:
    data_root, source_db, _receipt_path, _now = _formal_quick_fixture(tmp_path)
    plan = pipeline._technical_child_plan(
        data_root=data_root,
        source_db=source_db,
        source_date_start="2026-09-20",
        source_date_end="2026-09-20",
    )
    calendar_cache_path = tmp_path / "qa-calendar"
    temporary_closure_path = tmp_path / "qa-closures"

    arguments, _environment = pipeline._technical_child_invocation(
        data_root=data_root,
        plan=plan,
        base_environment={},
        window_weekdays=10,
        daily_delay_seconds=0.5,
        tpex_delay_seconds=0.5,
        broker_delay_seconds=0.5,
        skip_candidate_update=True,
        calendar_cache_path=calendar_cache_path,
        temporary_closure_path=temporary_closure_path,
    )
    parsed = pipeline.build_parser().parse_args(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(tmp_path / "shadow"),
            "--calendar-cache-path",
            str(calendar_cache_path),
            "--temporary-closure-path",
            str(temporary_closure_path),
        ]
    )

    assert parsed.calendar_cache_path == calendar_cache_path
    assert parsed.temporary_closure_path == temporary_closure_path
    assert arguments[arguments.index("--calendar-cache-path") + 1] == str(calendar_cache_path)
    assert arguments[arguments.index("--temporary-closure-path") + 1] == str(temporary_closure_path)
    assert "--skip-candidate-update" in arguments
    parsed_skip = pipeline.build_parser().parse_args(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(tmp_path / "shadow"),
            "--skip-candidate-update",
        ]
    )
    assert parsed_skip.skip_candidate_update is True


def test_explicit_skip_requires_existing_verified_reuse(monkeypatch, tmp_path: Path) -> None:
    data_root, source_db, receipt_path, now = _formal_quick_fixture(
        tmp_path,
        source_date_start="2026-09-15",
        source_date_end="2026-09-20",
    )
    plan = pipeline._formal_receipt_window_hint(
        data_root=data_root,
        source_db=source_db,
    )
    assert plan["status"] == "ready"
    assert pipeline._technical_window_matches_decision(
        plan,
        decision_date="2026-09-20",
        now=now,
    )
    import data_module.recommendation_calibration_source_contract as source_contract

    monkeypatch.setattr(
        source_contract,
        "reuse_verified_technical_computation_receipt",
        lambda **kwargs: {
            "status": "reused",
            "source_publication_receipt": {"path": str(receipt_path.resolve())},
            "source_date_start": "2026-09-15",
            "source_date_end": "2026-09-20",
        },
    )
    reuse = pipeline._verify_formal_technical_reuse(plan, now=now)
    assert reuse["status"] == "reused"

    monkeypatch.setattr(
        source_contract,
        "reuse_verified_technical_computation_receipt",
        lambda **kwargs: {
            "status": "not_found",
            "reason": "technical_output_current_value_mismatch",
        },
    )
    blocked = pipeline._verify_formal_technical_reuse(plan, now=now)
    assert blocked["status"] == "not_reused"
    assert blocked["reason"] == "technical_output_current_value_mismatch"


def test_pipeline_child_status_readback_uses_child_output_root(monkeypatch, tmp_path: Path) -> None:
    formal_root = (tmp_path / "formal-output").resolve()
    status_path = formal_root / "scheduled" / "data_update_quick" / "latest_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps({"status": "passed", "warnings": [], "blockers": []}),
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
        name="data_update_quick",
        script="scripts/scheduled/run_daily_data_update_quick.py",
        arguments=["--output-root", str(formal_root)],
        environment={
            "RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(formal_root),
            "OUTPUT_ROOT": str(formal_root),
        },
        log_handle=StringIO(),
        timeout_seconds=1.0,
    )

    assert result["status_path"] == str(status_path)
    assert result["child_status"]["status"] == "passed"


def test_pipeline_main_uses_real_same_day_multiday_reuse_and_formal_technical_child(
    monkeypatch, tmp_path: Path
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="ta-pipeline-", ignore_cleanup_errors=True
    ) as short_tmp:
        fixture_root = Path(short_tmp)
        data_root, source_db, publication = _multi_day_verified_publication(fixture_root)
        _write_formal_quick_pointer(data_root, publication)
        decision_now = datetime(2026, 9, 14, 14, 0, tzinfo=pipeline.TAIPEI)
        reuse = reuse_verified_technical_computation_receipt(
            authorized_output_roots=[data_root / "output"],
            source_db=source_db,
            source_date_start="2026-09-12",
            source_date_end="2026-09-14",
            availability_cutoff_at=decision_now,
        )
        assert reuse["status"] == "reused"
        assert reuse["source_date_start"] == "2026-09-12"
        assert reuse["source_date_end"] == "2026-09-14"

        _patch_pipeline_now(monkeypatch, decision_now)
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(pipeline, "_run_child", _fake_pipeline_child(calls))
        shadow_root = (tmp_path / "shadow-output").resolve()
        result = pipeline.main(
            [
                "--data-root",
                str(data_root),
                "--output-root",
                str(shadow_root),
                "--source-db",
                str(source_db),
                "--child-timeout-seconds",
                "10",
                "--pipeline-timeout-seconds",
                "60",
            ]
        )

        assert result == 0
        assert [call["name"] for call in calls] == [
            "data_update_quick",
            "official_market_events",
            "recommendation_snapshot",
            "recommendation_learning",
        ]
        technical_call = calls[0]
        technical_arguments = technical_call["arguments"]
        assert technical_arguments[technical_arguments.index("--output-root") + 1] == str(
            data_root / "output"
        )
        assert technical_arguments[
            technical_arguments.index("--formal-output-root") + 1
        ] == str(data_root / "output")
        assert technical_arguments[technical_arguments.index("--start-date") + 1] == "2026-09-12"
        assert technical_arguments[technical_arguments.index("--end-date") + 1] == "2026-09-14"
        assert technical_arguments[technical_arguments.index("--status-path") + 1] == str(
            data_root
            / "output"
            / "scheduled"
            / "data_update_quick"
            / "latest_status.json"
        )
        technical_environment = technical_call["environment"]
        assert technical_environment["OUTPUT_ROOT"] == str(data_root / "output")
        assert technical_environment["RECOMMENDATION_LEARNING_OUTPUT_ROOT"] == str(
            data_root / "output"
        )
        assert technical_environment["DB_PATH"] == str(source_db)
        for child_call in calls[1:]:
            assert child_call["environment"]["OUTPUT_ROOT"] == str(shadow_root)
            assert child_call["environment"]["RECOMMENDATION_LEARNING_OUTPUT_ROOT"] == str(
                shadow_root
            )
        learning_call = calls[-1]
        learning_arguments = learning_call["arguments"]
        assert learning_arguments[
            learning_arguments.index("--snapshot-output-root") + 1
        ] == str(shadow_root)
        assert learning_arguments[
            learning_arguments.index("--snapshot-result-id") + 1
        ] == "synthetic-snapshot-result"
        assert learning_arguments[
            learning_arguments.index("--snapshot-cohort-hash") + 1
        ] == "sha256:" + "a" * 64
        assert learning_arguments[
            learning_arguments.index("--snapshot-invocation-output-sha256") + 1
        ] == calls[2]["child_stdout_sha256"]
        gc.collect()


def test_pipeline_file_path_cli_inserts_repo_root_and_reaches_technical_reuse(
    tmp_path: Path,
) -> None:
    """直接以 file path 載入 pipeline 時，必須真的走到 technical reuse import。"""

    data_root, source_db, receipt_path, _now = _formal_quick_fixture(
        tmp_path / "direct-cli",
        source_date_start="2026-09-15",
        source_date_end="2026-09-20",
    )
    shadow_root = (tmp_path / "direct-cli-shadow").resolve()
    harness = (tmp_path / "direct_file_path_harness.py").resolve()
    harness.write_text(
        textwrap.dedent(
            """
            from pathlib import Path
            import json
            import runpy
            import sys
            from zoneinfo import ZoneInfo

            pipeline_path = Path(sys.argv[1]).resolve()
            data_root = Path(sys.argv[2]).resolve()
            source_db = Path(sys.argv[3]).resolve()
            receipt_path = Path(sys.argv[4]).resolve()
            shadow_root = Path(sys.argv[5]).resolve()
            repo_root = pipeline_path.parents[2]
            script_dir = pipeline_path.parent
            filtered = []
            for item in sys.path:
                if not item:
                    continue
                try:
                    if Path(item).resolve() == repo_root:
                        continue
                except (OSError, RuntimeError, ValueError):
                    pass
                filtered.append(item)
            sys.path = [str(script_dir), *filtered]
            root_before = str(repo_root) in sys.path
            namespace = runpy.run_path(str(pipeline_path), run_name="pipeline_under_test")
            pipeline_globals = namespace["main"].__globals__

            import data_module.recommendation_calibration_source_contract as source_contract

            reuse_calls = []
            def fake_reuse(**kwargs):
                reuse_calls.append(dict(kwargs))
                return {
                    "status": "reused",
                    "source_publication_receipt": {"path": str(receipt_path)},
                    "source_date_start": "2026-09-15",
                    "source_date_end": "2026-09-20",
                }

            source_contract.reuse_verified_technical_computation_receipt = fake_reuse

            base_datetime = pipeline_globals["datetime"]
            fixed_now = base_datetime(
                2026, 9, 20, 5, 45, tzinfo=ZoneInfo("America/Los_Angeles")
            )
            class FixedDateTime(base_datetime):
                @classmethod
                def now(cls, tz=None):
                    return fixed_now.astimezone(tz) if tz is not None else fixed_now.replace(tzinfo=None)

            pipeline_globals["datetime"] = FixedDateTime
            calls = []
            def fake_run_child(**kwargs):
                name = str(kwargs["name"])
                calls.append(name)
                child_root = Path(kwargs["environment"]["RECOMMENDATION_LEARNING_OUTPUT_ROOT"])
                status_path = pipeline_globals["_status_path"](child_root, name)
                child_status = {"status": "passed", "warnings": [], "blockers": []}
                if name == "recommendation_snapshot":
                    child_status["result_id"] = "synthetic-snapshot-result"
                    child_status["decision_date"] = pipeline_globals["datetime"].now(
                        pipeline_globals["TAIPEI"]
                    ).date().isoformat()
                    child_status["snapshot_cohort"] = {
                        "schema_version": "scheduled-recommendation-snapshot-cohort.v1",
                        "requested_symbols": ["1101"],
                        "eligible_symbols": ["1101"],
                        "missing_symbols": [],
                        "degraded_symbols": [],
                        "excluded_symbols": [],
                        "cohort_hash": "sha256:" + "a" * 64,
                    }
                    stdout_bytes = json.dumps(child_status, ensure_ascii=False).encode("utf-8")
                    artifact_path, artifact_size, artifact_hash = (
                        pipeline_globals["_write_snapshot_invocation_stdout_artifact"](
                            path=kwargs["snapshot_stdout_artifact_path"],
                            allowed_runs_root=kwargs["snapshot_stdout_runs_root"],
                            raw_stdout=stdout_bytes,
                        )
                    )
                else:
                    artifact_path = None
                    artifact_size = None
                    artifact_hash = None
                status_path.parent.mkdir(parents=True, exist_ok=True)
                status_path.write_text(json.dumps(child_status), encoding="utf-8")
                return {
                    "name": name,
                    "script": kwargs["script"],
                    "command": [],
                    "returncode": 0,
                    "status": "passed",
                    "status_path": str(status_path),
                    "child_status": child_status,
                    "child_status_source": "invocation_stdout_json",
                    "child_stdout_artifact_path": artifact_path,
                    "child_stdout_artifact_size": artifact_size,
                    "child_stdout_sha256": artifact_hash,
                    "child_warnings": [],
                    "child_blockers": [],
                    "stdout_stderr_tail": "",
                    "timeout_seconds": kwargs.get("timeout_seconds"),
                    "recoverable": False,
                }

            pipeline_globals["_run_child"] = fake_run_child
            result = namespace["main"]([
                "--data-root", str(data_root),
                "--output-root", str(shadow_root),
                "--source-db", str(source_db),
                "--child-timeout-seconds", "10",
                "--pipeline-timeout-seconds", "60",
            ])
            print("RESULT", result)
            print("ROOT_BEFORE", root_before)
            print("ROOT_AFTER", str(repo_root) in sys.path)
            print("REUSE_CALLS", len(reuse_calls))
            print("CHILDREN", ",".join(calls))
            """
        ),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("BALDR_PYTHON", None)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            str(harness),
            str(Path(pipeline.__file__).resolve()),
            str(data_root),
            str(source_db),
            str(receipt_path),
            str(shadow_root),
        ],
        cwd=str(tmp_path),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=30,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    assert completed.returncode == 0, output
    assert "RESULT 0" in output
    assert "ROOT_BEFORE False" in output
    assert "ROOT_AFTER True" in output
    assert "REUSE_CALLS 1" in output
    assert "CHILDREN data_update_quick,official_market_events,recommendation_snapshot,recommendation_learning" in output

    status_path = shadow_root / "scheduled" / "recommendation_calibration_learning" / "latest_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    terminal_receipt_path = Path(status["terminal_receipt_path"])
    assert status["status"] == "passed"
    assert terminal_receipt_path.is_file()
    assert status["terminal_receipt_sha256"] == (
        "sha256:" + hashlib.sha256(terminal_receipt_path.read_bytes()).hexdigest()
    )
    receipt = json.loads(terminal_receipt_path.read_text(encoding="utf-8"))
    assert receipt["terminal"] is True
    assert receipt["status"] == "passed"


def test_pipeline_file_path_cli_executes_as_main_without_pytest_path(
    tmp_path: Path,
) -> None:
    """以 file path／__main__ 執行，隔離 child 後仍須成功載入 reuse package。"""

    now = datetime.now(pipeline.TAIPEI)
    decision_date = now.date().isoformat()
    data_root, source_db, _receipt_path, _fixture_now = _formal_quick_fixture(
        tmp_path / "direct-main",
        available_at=(now.replace(microsecond=0)).isoformat(),
        source_date_start=decision_date,
        source_date_end=decision_date,
    )
    shadow_root = (tmp_path / "direct-main-shadow").resolve()
    harness = (tmp_path / "direct_main_harness.py").resolve()
    harness.write_text(
        textwrap.dedent(
            """
            from pathlib import Path
            import json
            import runpy
            import subprocess
            import sys
            from datetime import datetime
            from zoneinfo import ZoneInfo

            pipeline_path = Path(sys.argv[1]).resolve()
            data_root = Path(sys.argv[2]).resolve()
            source_db = Path(sys.argv[3]).resolve()
            shadow_root = Path(sys.argv[4]).resolve()
            repo_root = pipeline_path.parents[2]
            sys.path = [
                str(pipeline_path.parent),
                *[item for item in sys.path if item and Path(item).resolve() != repo_root],
            ]
            root_before = str(repo_root) in sys.path

            def fake_child(command, *args, **kwargs):
                script_name = Path(str(command[1])).name
                names = {
                    "run_official_market_event_backfill.py": "official_market_events",
                    "run_scheduled_recommendation_snapshot.py": "recommendation_snapshot",
                    "run_daily_recommendation_learning.py": "recommendation_learning",
                    "run_daily_data_update_quick.py": "data_update_quick",
                }
                name = names.get(script_name)
                if name:
                    child_root = Path(kwargs["env"]["RECOMMENDATION_LEARNING_OUTPUT_ROOT"])
                    status_path = (
                        child_root / "recommendation_learning" / "latest_status.json"
                        if name == "recommendation_learning"
                        else child_root / "scheduled" / name / "latest_status.json"
                    )
                    child_status = {"status": "passed", "warnings": [], "blockers": []}
                    if name == "recommendation_snapshot":
                        child_status["result_id"] = "synthetic-snapshot-result"
                        child_status["decision_date"] = datetime.now(
                            ZoneInfo("Asia/Taipei")
                        ).date().isoformat()
                        child_status["snapshot_cohort"] = {
                            "schema_version": "scheduled-recommendation-snapshot-cohort.v1",
                            "requested_symbols": ["1101"],
                            "eligible_symbols": ["1101"],
                            "missing_symbols": [],
                            "degraded_symbols": [],
                            "excluded_symbols": [],
                            "cohort_hash": "sha256:" + "a" * 64,
                        }
                    status_path.parent.mkdir(parents=True, exist_ok=True)
                    status_path.write_text(json.dumps(child_status), encoding="utf-8")
                stdout = (
                    json.dumps(
                        {
                            **child_status,
                            **({"task": "baldr-recommendation-snapshot-daily"} if name == "recommendation_snapshot" else {}),
                        }
                    ).encode("utf-8")
                    if name == "recommendation_snapshot"
                    else b""
                )
                return subprocess.CompletedProcess(command, 0, stdout, b"")

            subprocess.run = fake_child
            sys.argv = [
                str(pipeline_path),
                "--data-root", str(data_root),
                "--output-root", str(shadow_root),
                "--source-db", str(source_db),
                "--skip-technical-refresh",
                "--child-timeout-seconds", "10",
                "--pipeline-timeout-seconds", "60",
            ]
            try:
                runpy.run_path(str(pipeline_path), run_name="__main__")
            except SystemExit as exc:
                exit_code = exc.code
            else:
                exit_code = 0
            status_path = shadow_root / "scheduled" / "recommendation_calibration_learning" / "latest_status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            print("EXIT", exit_code)
            print("ROOT_BEFORE", root_before)
            print("ROOT_AFTER", str(repo_root) in sys.path)
            print("ERROR_TYPE", status.get("error_type"))
            print("TECHNICAL_STATUS", status["steps"]["data_update_quick"]["status"])
            """
        ),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("BALDR_PYTHON", None)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        [sys.executable, str(harness), str(Path(pipeline.__file__).resolve()), str(data_root), str(source_db), str(shadow_root)],
        cwd=str(tmp_path),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=30,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    assert completed.returncode == 0, output
    assert "ROOT_BEFORE False" in output
    assert "ROOT_AFTER True" in output
    assert "ERROR_TYPE ModuleNotFoundError" not in output
    assert "TECHNICAL_STATUS blocked" in output


def test_pipeline_unexpected_exception_writes_fail_closed_terminal_receipt(
    monkeypatch, tmp_path: Path
) -> None:
    data_root, source_db, _receipt_path, now = _formal_quick_fixture(
        tmp_path,
        source_date_start="2026-09-15",
        source_date_end="2026-09-20",
    )
    _patch_pipeline_now(monkeypatch, now)
    shadow_root = (tmp_path / "shadow-output").resolve()
    log_path = (
        shadow_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "20260920_pipeline.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("preexisting-child-log\n", encoding="utf-8")
    calls: list[str] = []

    def raise_import_error(*args, **kwargs):
        raise ModuleNotFoundError("No module named 'data_module'")

    monkeypatch.setattr(pipeline, "_verify_formal_technical_reuse", raise_import_error)
    monkeypatch.setattr(
        pipeline,
        "_run_child",
        lambda **kwargs: calls.append(str(kwargs["name"])) or pytest.fail("child must not start"),
    )
    result = pipeline.main(
        [
            "--data-root", str(data_root),
            "--output-root", str(shadow_root),
            "--source-db", str(source_db),
            "--child-timeout-seconds", "10",
            "--pipeline-timeout-seconds", "60",
        ]
    )

    assert result == 1
    assert calls == []
    status_path = shadow_root / "scheduled" / "recommendation_calibration_learning" / "latest_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["error_type"] == "ModuleNotFoundError"
    assert status["error"] == "No module named 'data_module'"
    assert status["failure_stage"] == "technical_reuse"
    assert "pipeline_exception:ModuleNotFoundError" in status["blockers"]
    terminal_receipt_path = Path(status["terminal_receipt_path"])
    assert terminal_receipt_path.is_file()
    assert status["terminal_receipt_sha256"] == (
        "sha256:" + hashlib.sha256(terminal_receipt_path.read_bytes()).hexdigest()
    )
    receipt = json.loads(terminal_receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "failed"
    assert receipt["failure_stage"] == "technical_reuse"
    assert receipt["terminal"] is True
    assert "preexisting-child-log" in log_path.read_text(encoding="utf-8")


def test_pipeline_receipt_write_failure_preserves_primary_exception(
    monkeypatch, tmp_path: Path
) -> None:
    data_root, source_db, _receipt_path, now = _formal_quick_fixture(
        tmp_path,
        source_date_start="2026-09-15",
        source_date_end="2026-09-20",
    )
    _patch_pipeline_now(monkeypatch, now)

    def raise_primary(*args, **kwargs):
        raise ModuleNotFoundError("No module named 'data_module'")

    def raise_receipt_error(*args, **kwargs):
        raise OSError("receipt volume unavailable")

    monkeypatch.setattr(pipeline, "_verify_formal_technical_reuse", raise_primary)
    monkeypatch.setattr(pipeline, "_write_terminal_receipt", raise_receipt_error)
    result = pipeline.main(
        [
            "--data-root", str(data_root),
            "--output-root", str((tmp_path / "shadow-output").resolve()),
            "--source-db", str(source_db),
            "--child-timeout-seconds", "10",
            "--pipeline-timeout-seconds", "60",
        ]
    )

    assert result == 1
    status_path = (
        tmp_path
        / "shadow-output"
        / "scheduled"
        / "recommendation_calibration_learning"
        / "latest_status.json"
    )
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["error_type"] == "ModuleNotFoundError"
    assert status["error"] == "No module named 'data_module'"
    assert status["failure_stage"] == "technical_reuse"
    assert status["terminal_receipt_error_type"] == "OSError"
    assert status["terminal_receipt_error"] == "receipt volume unavailable"
    assert "terminal_receipt_write_failed" in status["blockers"]
    assert not Path(status["terminal_receipt_path"]).exists()


@pytest.mark.parametrize(
    ("exception_type", "exception_argument"),
    [(KeyboardInterrupt, "interrupt"), (SystemExit, 7)],
    ids=["keyboard-interrupt", "system-exit"],
)
def test_pipeline_does_not_swallow_process_control_exceptions(
    monkeypatch,
    tmp_path: Path,
    exception_type: type[BaseException],
    exception_argument: object,
) -> None:
    data_root, source_db, _receipt_path, now = _formal_quick_fixture(
        tmp_path,
        source_date_start="2026-09-15",
        source_date_end="2026-09-20",
    )
    _patch_pipeline_now(monkeypatch, now)
    shadow_root = (tmp_path / "shadow-output").resolve()
    log_path = (
        shadow_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "20260920_pipeline.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("control-exception-log\n", encoding="utf-8")

    def raise_control_exception(*args, **kwargs):
        raise exception_type(exception_argument)

    monkeypatch.setattr(
        pipeline, "_verify_formal_technical_reuse", raise_control_exception
    )
    with pytest.raises(exception_type):
        pipeline.main(
            [
                "--data-root", str(data_root),
                "--output-root", str(shadow_root),
                "--source-db", str(source_db),
                "--child-timeout-seconds", "10",
                "--pipeline-timeout-seconds", "60",
            ]
        )

    status_path = shadow_root / "scheduled" / "recommendation_calibration_learning" / "latest_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["status"] == "running"
    assert not Path(status["terminal_receipt_path"]).exists()
    assert "control-exception-log" in log_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("receipt_state", ["missing", "stale"])
def test_pipeline_main_keeps_normal_refresh_on_decision_date_without_current_receipt(
    monkeypatch, tmp_path: Path, receipt_state: str
) -> None:
    if receipt_state == "missing":
        data_root = (tmp_path / "formal-data").resolve()
        source_db = (data_root / "sqlite" / "twstock.db").resolve()
    else:
        data_root, source_db, _receipt, _ = _formal_quick_fixture(tmp_path)
    decision_now = datetime(2026, 9, 21, 14, 0, tzinfo=pipeline.TAIPEI)
    _patch_pipeline_now(monkeypatch, decision_now)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(pipeline, "_run_child", _fake_pipeline_child(calls))
    result = pipeline.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str((tmp_path / "shadow-output").resolve()),
            "--source-db",
            str(source_db),
            "--child-timeout-seconds",
            "10",
            "--pipeline-timeout-seconds",
            "60",
        ]
    )

    assert result == 0
    technical_call = calls[0]
    arguments = technical_call["arguments"]
    assert arguments[arguments.index("--start-date") + 1] == "2026-09-21"
    assert arguments[arguments.index("--end-date") + 1] == "2026-09-21"
    assert technical_call["environment"]["OUTPUT_ROOT"] == str(data_root / "output")


def test_pipeline_main_blocks_custom_db_without_invoking_quick_writer(
    monkeypatch, tmp_path: Path
) -> None:
    data_root = (tmp_path / "formal-data").resolve()
    custom_db = (tmp_path / "custom.sqlite").resolve()
    custom_db.write_bytes(b"custom-db-bytes")
    before_bytes = custom_db.read_bytes()
    before_mtime_ns = custom_db.stat().st_mtime_ns
    _patch_pipeline_now(
        monkeypatch,
        datetime(2026, 9, 21, 14, 0, tzinfo=pipeline.TAIPEI),
    )
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(pipeline, "_run_child", _fake_pipeline_child(calls))
    result = pipeline.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str((tmp_path / "shadow-output").resolve()),
            "--source-db",
            str(custom_db),
            "--child-timeout-seconds",
            "10",
            "--pipeline-timeout-seconds",
            "60",
        ]
    )

    assert result == 1
    assert "data_update_quick" not in [call["name"] for call in calls]
    assert [call["name"] for call in calls] == [
        "official_market_events",
        "recommendation_snapshot",
        "recommendation_learning",
    ]
    assert custom_db.read_bytes() == before_bytes
    assert custom_db.stat().st_mtime_ns == before_mtime_ns


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
