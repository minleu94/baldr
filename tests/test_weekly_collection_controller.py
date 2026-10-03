from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
from types import SimpleNamespace

import pytest

from data_module import scheduled_research_acquisition_binding as binding
from scripts.scheduled import weekly_collection_controller as controller


def _publish_start(output_root: Path, *, run_id: str, started_at: datetime) -> tuple[Path, str]:
    relative = f"scheduled/v2_2_weekly_collection/controller_runs/{run_id}/start.json"
    path = output_root / Path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema_version": binding.WEEKLY_START_SCHEMA,
        "state": "running",
        "run_id": run_id,
        "receipt_relative_path": relative,
        "output_root": str(output_root.resolve()),
        "started_at_utc": started_at.isoformat(),
        "timing_budget_seconds": binding.weekly_timing_budget_seconds(),
    }
    raw = binding.canonical_json_bytes(receipt)
    path.write_bytes(raw)
    locator_path = output_root / binding.WEEKLY_LOCATOR_RELATIVE_PATH
    locator_path.parent.mkdir(parents=True, exist_ok=True)
    locator = {
        "schema_version": binding.WEEKLY_LOCATOR_SCHEMA,
        "state": "running",
        "run_id": run_id,
        "receipt": {"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "schema_version": binding.WEEKLY_START_SCHEMA},
        "started_at_utc": started_at.isoformat(),
        "updated_at_utc": started_at.isoformat(),
    }
    locator_path.write_bytes(binding.canonical_json_bytes(locator))
    return path, hashlib.sha256(raw).hexdigest()


def _prepare_sidecar(output_root: Path, source_db: Path, *, status: str = "pending_human_review") -> dict[str, object]:
    sidecar = output_root / "scheduled" / "v2_2_weekly_collection" / "evidence_scheduler.sqlite"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    source_hash = "sha256:" + "a" * 64
    record: dict[str, object] = {
        "collection_id": "ewc_test_001",
        "period_start": "2026-09-28",
        "period_end": "2026-10-03",
        "source_path": str(source_db.resolve()),
        "source_hash": source_hash,
        "status": status,
        "payload_json": {"source_access": "sqlite_uri_mode_ro", "write_intent": False},
        "error_type": "",
        "error_message": "",
        "created_at": "2026-10-03 08:00:00",
    }
    with sqlite3.connect(sidecar) as connection:
        connection.execute(
            """CREATE TABLE evidence_weekly_collections (
               collection_id TEXT PRIMARY KEY, period_start TEXT, period_end TEXT,
               source_path TEXT, source_hash TEXT, status TEXT, payload_json TEXT,
               error_type TEXT, error_message TEXT, created_at TEXT)"""
        )
        connection.execute(
            "INSERT INTO evidence_weekly_collections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record["collection_id"], record["period_start"], record["period_end"],
                record["source_path"], record["source_hash"], record["status"],
                json.dumps(record["payload_json"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                record["error_type"], record["error_message"], record["created_at"],
            ),
        )
    return record


def _core_stdout(record: dict[str, object]) -> bytes:
    return json.dumps(
        {
            "collection_status": record["status"],
            "human_approval_required": True,
            "automatic_revalidation": False,
            "write_intent": False,
            "source_db_path": record["source_path"],
            "collection_record": record,
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8") + b"\n"


def test_locator_running_boundary_uses_exact_receipt_and_clock(tmp_path):
    assert binding.WEEKLY_MAX_PENDING_SECONDS == (
        binding.WEEKLY_CORE_TIMEOUT_SECONDS
        + binding.WEEKLY_MONTHLY_QUERY_COUNT * binding.WEEKLY_MONTHLY_QUERY_TIMEOUT_SECONDS
        + binding.WEEKLY_QUARTERLY_RUN_TIMEOUT_SECONDS
        + binding.WEEKLY_SINGLE_BLOCKING_MARGIN_SECONDS
        + binding.WEEKLY_CONTROLLER_PUBLICATION_GRACE_SECONDS
    )
    assert binding.WEEKLY_MAX_PENDING_SECONDS == 1170
    started = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
    receipt_path, receipt_sha = _publish_start(tmp_path, run_id="run_boundary", started_at=started)
    at_boundary = binding.verify_weekly_acquisition(
        tmp_path, now=started + timedelta(seconds=binding.WEEKLY_MAX_PENDING_SECONDS)
    )
    over_boundary = binding.verify_weekly_acquisition(
        tmp_path, now=started + timedelta(seconds=binding.WEEKLY_MAX_PENDING_SECONDS + 1)
    )
    assert at_boundary["status"] == "pending"
    assert over_boundary["status"] == "blocked"
    assert over_boundary["reason"] == "weekly_controller_terminal_timeout"
    explicit = binding.verify_weekly_acquisition(
        tmp_path,
        now=started + timedelta(seconds=1),
        receipt_path=receipt_path,
        expected_sha256=receipt_sha,
    )
    assert explicit["status"] == "pending"
    assert binding.verify_weekly_acquisition(
        tmp_path, now=started, receipt_path=receipt_path
    )["reason"] == "external_receipt_path_sha_pair_incomplete"


def test_locator_missing_and_same_shape_historical_run_swap_are_not_current(tmp_path):
    now = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
    assert binding.verify_weekly_acquisition(tmp_path, now=now)["status"] == "not_recorded"
    receipt_path, _ = _publish_start(tmp_path, run_id="old_valid_run", started_at=now - timedelta(days=7))
    # locator's exact old start still means a pending old run, never a terminal success.
    result = binding.verify_weekly_acquisition(tmp_path, now=now)
    assert result["status"] == "blocked"
    assert result["reason"] == "weekly_controller_terminal_timeout"
    assert receipt_path.name == "start.json"


def test_controller_publishes_and_rechecks_core_sidecar_without_children(tmp_path):
    output_root = tmp_path / "data" / "output"
    output_root.mkdir(parents=True)
    source_db = tmp_path / "data" / "sqlite" / "source.sqlite"
    source_db.parent.mkdir(parents=True)
    source_db.write_bytes(b"source fixture")
    record = _prepare_sidecar(output_root, source_db)
    calls = 0

    def fake_runner(command, **kwargs):
        nonlocal calls
        calls += 1
        assert "collect_v2_2_weekly_evidence.py" in command[1]
        assert kwargs["timeout"] == binding.WEEKLY_CORE_TIMEOUT_SECONDS
        return SimpleNamespace(returncode=0, stdout=_core_stdout(record), stderr=b"")

    start = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
    clocks = iter((start, start + timedelta(minutes=2)))
    exit_code, result = controller.run_controller(
        source_db_path=source_db,
        sidecar_db_path=output_root / "scheduled" / "v2_2_weekly_collection" / "evidence_scheduler.sqlite",
        output_root=output_root,
        repository_root=tmp_path,
        runner=fake_runner,
        now=lambda: next(clocks),
        environ={"BALDR_ENABLE_MOPS_STATEMENT_CUSTODY": "0", "BALDR_ENABLE_MOPS_QUARTERLY_OPENAPI_RESEARCH": "0"},
    )
    assert exit_code == 0
    assert calls == 1
    assert result["locator_published"] is True
    latest = binding.verify_weekly_acquisition(output_root, now=start + timedelta(minutes=3), repository_root=tmp_path)
    assert latest["status"] == "verified"
    assert latest["collection_id"] == record["collection_id"]
    assert latest["human_review_required"] is True
    assert latest["formal_credit"] is False


def test_child_timeout_keeps_partial_bytes_and_still_preserves_core_exit(tmp_path):
    output_root = tmp_path / "data" / "output"
    output_root.mkdir(parents=True)
    source_db = tmp_path / "data" / "sqlite" / "source.sqlite"
    source_db.parent.mkdir(parents=True)
    source_db.write_bytes(b"source fixture")
    record = _prepare_sidecar(output_root, source_db)
    calls = 0

    def fake_runner(command, **kwargs):
        nonlocal calls
        calls += 1
        if "collect_v2_2_weekly_evidence.py" in command[1]:
            return SimpleNamespace(returncode=0, stdout=_core_stdout(record), stderr=b"")
        assert kwargs["timeout"] == binding.WEEKLY_MONTHLY_TIMEOUT_SECONDS == 180
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=b"{\"partial\"", stderr=b"timeout")

    # Reuse the row already present in SQLite while keeping the fake core output exact.
    start = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
    clocks = iter((start, start + timedelta(minutes=4)))
    exit_code, result = controller.run_controller(
        source_db_path=source_db,
        sidecar_db_path=output_root / "scheduled" / "v2_2_weekly_collection" / "evidence_scheduler.sqlite",
        output_root=output_root,
        repository_root=tmp_path,
        runner=fake_runner,
        now=lambda: next(clocks),
        environ={"BALDR_ENABLE_MOPS_STATEMENT_CUSTODY": "1", "BALDR_ENABLE_MOPS_QUARTERLY_OPENAPI_RESEARCH": "0"},
    )
    assert exit_code == 0
    assert calls == 2
    stdout_path = output_root / result["receipt_path"]
    terminal = json.loads(stdout_path.read_text(encoding="utf-8"))
    child = terminal["children"]["monthly_statement"]
    assert child["status"] == "failed"
    assert child["timed_out"] is True
    partial_path = output_root / child["stdout"]["path"]
    assert partial_path.read_bytes() == b"{\"partial\""
    readback = binding.verify_weekly_acquisition(output_root, now=start + timedelta(minutes=5), repository_root=tmp_path)
    assert readback["status"] == "partial"
    assert readback["child_failures"] == ["monthly_statement"]


def test_quarterly_child_uses_run_gate_plus_one_blocking_margin(tmp_path):
    output_root = tmp_path / "data" / "output"
    output_root.mkdir(parents=True)
    source_db = tmp_path / "data" / "sqlite" / "source.sqlite"
    source_db.parent.mkdir(parents=True)
    source_db.write_bytes(b"source fixture")
    record = _prepare_sidecar(output_root, source_db)
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        if "collect_v2_2_weekly_evidence.py" in command[1]:
            assert kwargs["timeout"] == binding.WEEKLY_CORE_TIMEOUT_SECONDS
            return SimpleNamespace(returncode=0, stdout=_core_stdout(record), stderr=b"")
        assert "capture_mops_quarterly_openapi_research.py" in command[1]
        assert kwargs["timeout"] == binding.WEEKLY_QUARTERLY_TIMEOUT_SECONDS == 930
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=b"quarter partial", stderr=b"quarter deadline")

    start = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
    clocks = iter((start, start + timedelta(seconds=931)))
    exit_code, result = controller.run_controller(
        source_db_path=source_db,
        sidecar_db_path=output_root / "scheduled" / "v2_2_weekly_collection" / "evidence_scheduler.sqlite",
        output_root=output_root,
        repository_root=tmp_path,
        runner=fake_runner,
        now=lambda: next(clocks),
        environ={"BALDR_ENABLE_MOPS_STATEMENT_CUSTODY": "0", "BALDR_ENABLE_MOPS_QUARTERLY_OPENAPI_RESEARCH": "1"},
    )
    assert exit_code == 0
    assert len(calls) == 2
    terminal = json.loads(Path(result["receipt_path"]).read_text(encoding="utf-8"))
    child = terminal["children"]["quarterly_openapi"]
    assert child["status"] == "failed"
    assert child["timed_out"] is True
    assert (output_root / child["stdout"]["path"]).read_bytes() == b"quarter partial"
    readback = binding.verify_weekly_acquisition(
        output_root,
        now=start + timedelta(seconds=932),
        repository_root=tmp_path,
    )
    assert readback["status"] == "partial"
    assert readback["child_failures"] == ["quarterly_openapi"]


def test_controller_completion_unknown_clock_is_not_fabricated(tmp_path):
    output_root = tmp_path / "data" / "output"
    output_root.mkdir(parents=True)
    source_db = tmp_path / "data" / "sqlite" / "source.sqlite"
    source_db.parent.mkdir(parents=True)
    source_db.write_bytes(b"source fixture")
    record = _prepare_sidecar(output_root, source_db)
    def fake_runner(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout=_core_stdout(record), stderr=b"")
    clocks = iter((datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc), datetime(2026, 10, 3, 8, 1)))
    controller.run_controller(
        source_db_path=source_db,
        sidecar_db_path=output_root / "scheduled" / "v2_2_weekly_collection" / "evidence_scheduler.sqlite",
        output_root=output_root,
        repository_root=tmp_path,
        runner=fake_runner,
        now=lambda: next(clocks),
        environ={"BALDR_ENABLE_MOPS_STATEMENT_CUSTODY": "0", "BALDR_ENABLE_MOPS_QUARTERLY_OPENAPI_RESEARCH": "0"},
    )
    locator = json.loads((output_root / binding.WEEKLY_LOCATOR_RELATIVE_PATH).read_text(encoding="utf-8"))
    terminal_path = output_root / locator["receipt"]["path"]
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert terminal["completed_at_utc"] is None
    assert terminal["controller_clock_reason"] == "controller_completion_clock_invalid"
    assert terminal["completion_clock_observation"] == {
        "status": "unknown",
        "observed_type": "datetime",
        "observed_raw": "2026-10-03T08:01:00",
        "reason": "clock_timezone_missing",
    }
    result = binding.verify_weekly_acquisition(output_root, now=datetime(2026, 10, 3, 8, 2, tzinfo=timezone.utc), repository_root=tmp_path)
    assert result["status"] == "blocked"
    assert result["reason"] == "weekly_controller_clock_invalid"
    # 模擬舊 consumer 只看 completed_at：即使 reason 被拿掉、完成時間偽裝成 start，
    # observation 仍標示 unknown，讀取端必須繼續拒絕。
    terminal["completed_at_utc"] = terminal["started_at_utc"]
    terminal["controller_clock_reason"] = None
    terminal_raw = binding.canonical_json_bytes(terminal)
    terminal_path.write_bytes(terminal_raw)
    locator["receipt"]["sha256"] = hashlib.sha256(terminal_raw).hexdigest()
    locator["updated_at_utc"] = terminal["started_at_utc"]
    (output_root / binding.WEEKLY_LOCATOR_RELATIVE_PATH).write_bytes(binding.canonical_json_bytes(locator))
    result = binding.verify_weekly_acquisition(
        output_root,
        now=datetime(2026, 10, 3, 8, 2, tzinfo=timezone.utc),
        repository_root=tmp_path,
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "weekly_controller_clock_observation_invalid"


def test_controller_completion_clock_exception_is_unknown_and_reader_blocks(tmp_path):
    output_root = tmp_path / "data" / "output"
    output_root.mkdir(parents=True)
    source_db = tmp_path / "data" / "sqlite" / "source.sqlite"
    source_db.parent.mkdir(parents=True)
    source_db.write_bytes(b"source fixture")
    record = _prepare_sidecar(output_root, source_db)

    def fake_runner(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout=_core_stdout(record), stderr=b"")

    calls = 0
    def clock():
        nonlocal calls
        calls += 1
        if calls == 1:
            return datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
        raise OSError("clock unavailable")

    controller.run_controller(
        source_db_path=source_db,
        sidecar_db_path=output_root / "scheduled" / "v2_2_weekly_collection" / "evidence_scheduler.sqlite",
        output_root=output_root,
        repository_root=tmp_path,
        runner=fake_runner,
        now=clock,
        environ={"BALDR_ENABLE_MOPS_STATEMENT_CUSTODY": "0", "BALDR_ENABLE_MOPS_QUARTERLY_OPENAPI_RESEARCH": "0"},
    )
    locator = json.loads((output_root / binding.WEEKLY_LOCATOR_RELATIVE_PATH).read_text(encoding="utf-8"))
    terminal_path = output_root / locator["receipt"]["path"]
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert terminal["completed_at_utc"] is None
    assert terminal["completion_clock_observation"] == {
        "status": "unknown",
        "observed_type": "unavailable",
        "observed_raw": None,
        "reason": "controller_completion_clock_unavailable",
        "error_type": "OSError",
    }
    result = binding.verify_weekly_acquisition(
        output_root,
        now=datetime(2026, 10, 3, 8, 2, tzinfo=timezone.utc),
        repository_root=tmp_path,
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "weekly_controller_clock_invalid"


def test_core_timeout_preserves_partial_streams_skips_children_and_fails(tmp_path):
    output_root = tmp_path / "data" / "output"
    output_root.mkdir(parents=True)
    source_db = tmp_path / "data" / "sqlite" / "source.sqlite"
    source_db.parent.mkdir(parents=True)
    source_db.write_bytes(b"source fixture")
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        assert kwargs["timeout"] == binding.WEEKLY_CORE_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=b"partial core", stderr=b"core deadline")

    start = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
    clocks = iter((start, start + timedelta(seconds=31)))
    exit_code, result = controller.run_controller(
        source_db_path=source_db,
        sidecar_db_path=output_root / "scheduled" / "v2_2_weekly_collection" / "evidence_scheduler.sqlite",
        output_root=output_root,
        repository_root=tmp_path,
        runner=fake_runner,
        now=lambda: next(clocks),
        environ={"BALDR_ENABLE_MOPS_STATEMENT_CUSTODY": "1", "BALDR_ENABLE_MOPS_QUARTERLY_OPENAPI_RESEARCH": "1"},
    )
    assert exit_code == 2
    assert len(calls) == 1
    terminal_path = Path(result["receipt_path"])
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert terminal["core"]["timed_out"] is True
    assert terminal["children"]["monthly_statement"]["status"] == "skipped"
    assert terminal["children"]["quarterly_openapi"]["status"] == "skipped"
    assert (output_root / terminal["core"]["stdout"]["path"]).read_bytes() == b"partial core"
    assert (output_root / terminal["core"]["stderr"]["path"]).read_bytes() == b"core deadline"
    readback = binding.verify_weekly_acquisition(
        output_root,
        now=start + timedelta(seconds=32),
        repository_root=tmp_path,
    )
    assert readback["status"] == "failed", readback
    assert readback["reason"] == "weekly_core_process_timeout"


def test_controller_cli_help_is_read_only_and_names_required_roots():
    help_text = controller.build_parser().format_help()
    assert "--source-db-path" in help_text
    assert "--sidecar-db-path" in help_text
    assert "--output-root" in help_text


def test_weekly_cmd_delegates_to_controller_and_keeps_original_root_defaults():
    command = (controller.REPO_ROOT / "scripts" / "scheduled" / "run_v2_2_weekly_collection.cmd").read_text(encoding="utf-8")
    assert "weekly_collection_controller.py" in command
    assert "BALDR_ENABLE_MOPS_STATEMENT_CUSTODY" not in command or "controller" in command
    assert "D:\\Min\\Python\\Project\\FA_Data" in command
    assert "evidence_scheduler.db" in command


@pytest.mark.parametrize("exit_value", [True, "0", None])
def test_weekly_core_exit_code_rejects_bool_and_non_integer(exit_value):
    with pytest.raises(binding.ResearchBindingError, match="exit_code_must_be_int"):
        binding._receipt_status({"core": {"exit_code": exit_value}, "children": {}})


def test_unknown_weekly_child_state_fails_closed(tmp_path):
    receipt = {"children": {"monthly_statement": {"status": "maybe", "stdout": {"path": "x", "sha256": "a" * 64, "bytes": 1}}, "quarterly_openapi": {"status": "skipped"}}}
    with pytest.raises(binding.ResearchBindingError, match="status_invalid"):
        binding._verify_weekly_child_bindings(tmp_path, tmp_path, receipt)


def test_current_weekly_parent_rejects_swapped_valid_historical_quarterly_terminal(tmp_path):
    output_root = tmp_path / "FA_Data" / "output"
    repository_root = tmp_path
    stdout_path = output_root / "scheduled" / "v2_2_weekly_collection" / "controller_runs" / "current" / "quarterly.stdout.json"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    run_root = repository_root / "output" / "mops_quarterly_openapi_research" / "old-run"
    run_root.mkdir(parents=True)
    terminal_path = run_root / "collector_terminal.json"
    old_terminal = {
        "schema_version": "mops-quarterly-openapi-research-terminal.v1",
        "run_id": "old-run",
        "run_root": str(run_root),
        "status": "completed_observation_only",
        "captured_at_utc": "2026-10-03T08:01:00+00:00",
        "verification_completed_at_utc": "2026-10-03T08:00:50+00:00",
        "research_artifact_materialized_at_utc": "2026-10-03T08:00:55+00:00",
        "research_artifact_readback_verified_at_utc": "2026-10-03T08:00:50+00:00",
        "candidate_available_at": None,
        "formal_pit_eligible": False,
        "issuer_coverage_complete": False,
        "readback": {
            "run_id": "old-run",
            "numeric_rows_rechecked": 24,
            "formal_pit_eligible": False,
            "issuer_coverage_complete": False,
        },
    }
    terminal_raw = binding.canonical_json_bytes(old_terminal)
    terminal_path.write_bytes(terminal_raw)
    stdout_raw = json.dumps({"run_id": "current-run", "run_root": str(run_root), "started_at_utc": "2026-10-03T08:00:00+00:00", "status": "completed_observation_only"}).encode()
    stdout_path.write_bytes(stdout_raw)
    receipt = {
        "started_at_utc": "2026-10-03T07:59:00+00:00",
        "completed_at_utc": "2026-10-03T08:02:00+00:00",
        "children": {
            "monthly_statement": {"status": "skipped"},
            "quarterly_openapi": {
                "status": "completed_observation_only",
                "raw_status": "completed_observation_only",
                "run_id": "current-run",
                "run_root": str(run_root),
                "process_exit_code": 0,
                "stdout": {"path": stdout_path.relative_to(output_root).as_posix(), "sha256": hashlib.sha256(stdout_raw).hexdigest(), "bytes": len(stdout_raw)},
                "terminal": {"path": str(terminal_path), "sha256": hashlib.sha256(terminal_raw).hexdigest(), "bytes": len(terminal_raw), "schema_version": "mops-quarterly-openapi-research-terminal.v1", "run_id": "old-run"},
            },
        },
    }
    with pytest.raises(binding.ResearchBindingError, match="run_id_mismatch"):
        binding._verify_weekly_child_bindings(output_root, repository_root, receipt)


def _monthly_binding_fixture(tmp_path, *, declared_artifact_sha: str):
    repository_root = tmp_path
    output_root = tmp_path / "FA_Data" / "output"
    output_root.mkdir(parents=True)
    run_id = "run_weekly_fixture"
    run_root = repository_root / "output" / "research" / "mops_statement_availability" / run_id
    run_root.mkdir(parents=True)
    artifact = run_root / "candidate.json"
    artifact_raw = b'{"candidate_rows":1}\n'
    artifact.write_bytes(artifact_raw)
    mapping = run_root / "mapping.csv"
    mapping_raw = b"source,target\n"
    mapping.write_bytes(mapping_raw)
    status = {
        "schema_version": "mops-weekly-research-capture-status.v1",
        "run_id": run_id,
        "status": "captured_research",
        "artifact_path": str(artifact),
        "artifact_sha256": declared_artifact_sha,
        "collection_started_at_utc": "2026-10-03T08:00:00+00:00",
        "collection_completed_at_utc": "2026-10-03T08:01:00+00:00",
        "formal_oos_allowed": False,
        "formal_credit_authorized": False,
        "source_readback_status": "not_enabled",
    }
    (run_root / "weekly_research_status.json").write_bytes(binding.canonical_json_bytes(status))
    stdout_payload = {
        "status": "captured_research",
        "weekly_research_status": "captured_research",
        "artifact_path": str(artifact),
        "mapping_path": str(mapping),
    }
    stdout_raw = json.dumps(stdout_payload, sort_keys=True).encode("utf-8") + b"\n"
    stdout_path = output_root / "scheduled/v2_2_weekly_collection/controller_runs/run/monthly.stdout.json"
    stderr_path = output_root / "scheduled/v2_2_weekly_collection/controller_runs/run/monthly.stderr.txt"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_bytes(stdout_raw)
    stderr_path.write_bytes(b"")
    process_pins = {
        "stdout": {
            "path": stdout_path.relative_to(output_root).as_posix(),
            "sha256": hashlib.sha256(stdout_raw).hexdigest(),
            "bytes": len(stdout_raw),
        },
        "stderr": {
            "path": stderr_path.relative_to(output_root).as_posix(),
            "sha256": hashlib.sha256(b"").hexdigest(),
            "bytes": 0,
        },
    }
    item = controller._monthly_child_binding(
        exit_code=0,
        summary={
            "weekly_research_status": "captured_research",
            "artifact_path": str(artifact),
            "mapping_path": str(mapping),
        },
        process_pins=process_pins,
        repository_root=repository_root,
    )
    receipt = {
        "started_at_utc": "2026-10-03T07:59:00+00:00",
        "completed_at_utc": "2026-10-03T08:02:00+00:00",
        "children": {"monthly_statement": item, "quarterly_openapi": {"status": "skipped"}},
    }
    return output_root, repository_root, item, receipt, stdout_path


def test_monthly_prefixed_artifact_sha_is_bound_through_controller_and_verifier(tmp_path):
    raw = b'{"candidate_rows":1}\n'
    declared = "sha256:" + hashlib.sha256(raw).hexdigest()
    output_root, repository_root, item, receipt, _ = _monthly_binding_fixture(
        tmp_path,
        declared_artifact_sha=declared,
    )

    assert item["status"] == "captured_research"
    assert item["artifact"]["sha256"] == hashlib.sha256(raw).hexdigest()
    result = binding._verify_weekly_child_bindings(output_root, repository_root, receipt)
    assert result["monthly_statement"]["status"] == "captured_verified"


def test_monthly_invalid_prefixed_artifact_sha_stays_blocked_and_raw_bound(tmp_path):
    output_root, repository_root, item, receipt, stdout_path = _monthly_binding_fixture(
        tmp_path,
        declared_artifact_sha="sha256:" + "g" * 64,
    )

    assert item["status"] == "blocked"
    assert "sha256_missing_or_invalid" in item["reason"]
    result = binding._verify_weekly_child_bindings(output_root, repository_root, receipt)
    assert result["monthly_statement"]["status"] == "blocked"
    assert result["monthly_statement"]["reason"] == item["reason"]
    assert result["monthly_statement"]["process_exit_code"] == 0

    stdout_path.write_bytes(b"tampered")
    with pytest.raises(binding.ResearchBindingError, match="bytes_pin_mismatch"):
        binding._verify_weekly_child_bindings(output_root, repository_root, receipt)


def test_blocked_monthly_child_preserves_raw_non_json_stdout_pin(tmp_path):
    output_root, repository_root, item, receipt, stdout_path = _monthly_binding_fixture(
        tmp_path,
        declared_artifact_sha="sha256:" + "g" * 64,
    )
    raw_stdout = b"child emitted partial non-json output"
    stdout_path.write_bytes(raw_stdout)
    item["stdout"] = {
        **item["stdout"],
        "sha256": hashlib.sha256(raw_stdout).hexdigest(),
        "bytes": len(raw_stdout),
    }

    result = binding._verify_weekly_child_bindings(output_root, repository_root, receipt)

    assert result["monthly_statement"]["status"] == "blocked"
    assert result["monthly_statement"]["reason"] == item["reason"]
    assert result["monthly_statement"]["stdout_sha256"] == hashlib.sha256(raw_stdout).hexdigest()


def test_blocked_monthly_child_does_not_skip_quarterly_verification(monkeypatch, tmp_path):
    output_root, repository_root, monthly, receipt, _ = _monthly_binding_fixture(
        tmp_path,
        declared_artifact_sha="sha256:" + "g" * 64,
    )
    quarterly_run_root = repository_root / "output" / "mops_quarterly_openapi_research" / "quarter_run"
    quarterly_run_root.mkdir(parents=True)
    quarterly_stdout = output_root / "scheduled/v2_2_weekly_collection/controller_runs/run/quarterly.stdout.json"
    readback = {
        "run_id": "quarter_run",
        "numeric_rows_rechecked": 1,
        "formal_pit_eligible": False,
        "issuer_coverage_complete": False,
    }
    terminal = {
        "schema_version": "mops-quarterly-openapi-research-terminal.v1",
        "run_id": "quarter_run",
        "run_root": str(quarterly_run_root),
        "status": "completed_with_review_items",
        "captured_at_utc": "2026-10-03T08:01:00+00:00",
        "verification_completed_at_utc": "2026-10-03T08:00:50+00:00",
        "research_artifact_materialized_at_utc": "2026-10-03T08:00:55+00:00",
        "research_artifact_readback_verified_at_utc": "2026-10-03T08:00:50+00:00",
        "candidate_available_at": None,
        "formal_pit_eligible": False,
        "issuer_coverage_complete": False,
        "readback": readback,
    }
    quarterly_stdout_payload = {
        "run_id": "quarter_run",
        "run_root": str(quarterly_run_root),
        "started_at_utc": "2026-10-03T08:00:00+00:00",
        "status": terminal["status"],
        "terminal": terminal,
    }
    stdout_raw = binding.canonical_json_bytes(quarterly_stdout_payload)
    quarterly_stdout.write_bytes(stdout_raw)
    terminal_path = quarterly_run_root / "collector_terminal.json"
    terminal_raw = binding.canonical_json_bytes(terminal)
    terminal_path.write_bytes(terminal_raw)
    receipt["children"]["quarterly_openapi"] = {
        "status": "completed_with_review_items",
        "raw_status": "completed_with_review_items",
        "run_id": "quarter_run",
        "run_root": str(quarterly_run_root),
        "process_exit_code": 0,
        "stdout": {
            "path": quarterly_stdout.relative_to(output_root).as_posix(),
            "sha256": hashlib.sha256(stdout_raw).hexdigest(),
            "bytes": len(stdout_raw),
        },
        "terminal": {
            "path": str(terminal_path),
            "sha256": hashlib.sha256(terminal_raw).hexdigest(),
            "bytes": len(terminal_raw),
            "schema_version": terminal["schema_version"],
            "run_id": "quarter_run",
        },
    }
    from data_module import mops_quarterly_openapi_research_capture

    monkeypatch.setattr(
        mops_quarterly_openapi_research_capture,
        "verify_capture_run",
        lambda _: terminal["readback"],
    )

    result = binding._verify_weekly_child_bindings(output_root, repository_root, receipt)

    assert monthly["status"] == "blocked"
    assert result["monthly_statement"]["status"] == "blocked"
    assert result["quarterly_openapi"]["status"] == "captured_with_review"


def _quarterly_terminal_binding_fixture(
    tmp_path,
    monkeypatch,
    *,
    status="blocked_catalog_contract_or_transport",
    exit_code=2,
    terminal_changes=None,
    summary_changes=None,
):
    repository_root = tmp_path
    output_root = tmp_path / "FA_Data" / "output"
    child_id = "quarterly-current-run"
    run_root = repository_root / "output" / "mops_quarterly_openapi_research" / child_id
    run_root.mkdir(parents=True)
    readback = {
        "run_id": child_id,
        "artifact_count": 4,
        "request_receipts_verified": 2,
        "catalog_contracts_revalidated": 2,
        "numeric_rows_rechecked": 0,
        "preview_rows_rechecked": 0,
        "issuer_coverage_complete": False,
        "formal_pit_eligible": False,
    }
    terminal = {
        "schema_version": "mops-quarterly-openapi-research-terminal.v1",
        "run_id": child_id,
        "run_root": str(run_root),
        "status": status,
        "verification_completed_at_utc": "2026-10-03T08:00:50+00:00",
        "research_artifact_materialized_at_utc": "2026-10-03T08:00:55+00:00",
        "research_artifact_readback_verified_at_utc": "2026-10-03T08:00:50+00:00",
        "captured_at_utc": "2026-10-03T08:01:00+00:00",
        "candidate_available_at": None,
        "candidate_available_at_reason": "source disclosure availability is unknown",
        "formal_pit_eligible": False,
        "issuer_coverage_complete": False,
        "readback": readback,
    }
    terminal.update(terminal_changes or {})
    terminal_path = run_root / "collector_terminal.json"
    terminal_raw = binding.canonical_json_bytes(terminal)
    terminal_path.write_bytes(terminal_raw)

    summary = {
        "schema_version": "mops-quarterly-openapi-research-run.v1",
        "run_id": child_id,
        "run_root": str(run_root),
        "started_at_utc": "2026-10-03T08:00:00+00:00",
        "status": status,
        "terminal": terminal,
    }
    summary.update(summary_changes or {})
    stdout_path = output_root / "scheduled" / "v2_2_weekly_collection" / "controller_runs" / "weekly-run" / "quarterly.stdout.json"
    stderr_path = stdout_path.with_name("quarterly.stderr.txt")
    stdout_path.parent.mkdir(parents=True)
    stdout_raw = binding.canonical_json_bytes(summary)
    stderr_raw = b""
    stdout_path.write_bytes(stdout_raw)
    stderr_path.write_bytes(stderr_raw)
    process_pins = {
        "stdout": {
            "path": stdout_path.relative_to(output_root).as_posix(),
            "sha256": hashlib.sha256(stdout_raw).hexdigest(),
            "bytes": len(stdout_raw),
        },
        "stderr": {
            "path": stderr_path.relative_to(output_root).as_posix(),
            "sha256": hashlib.sha256(stderr_raw).hexdigest(),
            "bytes": len(stderr_raw),
        },
    }
    from data_module import mops_quarterly_openapi_research_capture

    monkeypatch.setattr(
        mops_quarterly_openapi_research_capture,
        "verify_capture_run",
        lambda _: readback,
    )
    item = controller._quarterly_child_binding(
        exit_code=exit_code,
        summary=summary,
        process_pins=process_pins,
        repository_root=repository_root,
    )
    receipt = {
        "started_at_utc": "2026-10-03T07:59:00+00:00",
        "completed_at_utc": "2026-10-03T08:02:00+00:00",
        "core": {"exit_code": 0},
        "children": {
            "monthly_statement": {"status": "skipped"},
            "quarterly_openapi": item,
        },
    }
    return output_root, repository_root, terminal, readback, item, receipt


@pytest.mark.parametrize(
    "status",
    sorted(binding.WEEKLY_QUARTERLY_PUBLISHED_FAILURE_STATES),
)
def test_published_quarterly_negative_terminal_is_bound_as_partial_failure(
    monkeypatch, tmp_path, status
):
    from data_module import mops_quarterly_openapi_research_capture

    output_root, repository_root, terminal, readback, item, receipt = (
        _quarterly_terminal_binding_fixture(tmp_path, monkeypatch, status=status, exit_code=2)
    )

    assert item["status"] == "failed"
    assert item["raw_status"] == status
    assert item["reason"] == status
    assert item["process_exit_code"] == 2
    result = binding._verify_weekly_child_bindings(output_root, repository_root, receipt)
    assert result["quarterly_openapi"]["status"] == "failed"
    assert result["quarterly_openapi"]["producer_status"] == status
    assert binding._receipt_status(receipt)["status"] == "partial"
    assert terminal["formal_pit_eligible"] is False


@pytest.mark.parametrize(
    ("terminal_changes", "exit_code", "summary_changes", "expected_reason"),
    [
        ({"status": "unrecognized_negative"}, 2, {}, "weekly_quarterly_terminal_status_invalid"),
        ({"formal_pit_eligible": True}, 2, {}, "weekly_quarterly_qualification_boundary_changed"),
        ({"issuer_coverage_complete": True}, 2, {}, "weekly_quarterly_qualification_boundary_changed"),
        ({"captured_at_utc": "2026-10-03T08:01:00"}, 2, {}, "weekly_quarterly_captured_at_must_be_aware"),
        ({"verification_completed_at_utc": "1970-01-01T00:00:00+00:00", "research_artifact_readback_verified_at_utc": "1970-01-01T00:00:00+00:00", "research_artifact_materialized_at_utc": "1970-01-01T00:00:00+00:00"}, 2, {}, "weekly_quarterly_terminal_clock_order_invalid"),
        ({"readback": {"run_id": "wrong", "formal_pit_eligible": False, "issuer_coverage_complete": False}}, 2, {}, "weekly_quarterly_terminal_readback_contract_changed"),
        ({}, True, {}, "weekly_quarterly_exit_code_must_be_int"),
        ({}, 0, {}, "weekly_quarterly_process_status_mismatch"),
        ({}, 2, {"run_id": "historic-run"}, "weekly_quarterly_terminal_run_id_mismatch"),
        ({}, 2, {"status": "collector_internal_error"}, "quarterly_stdout_status_mismatch"),
    ],
)
def test_quarterly_unpublished_or_malformed_terminal_stays_blocked(
    monkeypatch, tmp_path, terminal_changes, exit_code, summary_changes, expected_reason
):
    _, _, _, _, item, _ = _quarterly_terminal_binding_fixture(
        tmp_path,
        monkeypatch,
        terminal_changes=terminal_changes,
        exit_code=exit_code,
        summary_changes=summary_changes,
    )
    assert item["status"] == "blocked"
    assert expected_reason in item["reason"]
    assert "terminal" not in item


def test_quarterly_child_clock_must_fit_parent_window(monkeypatch, tmp_path):
    from data_module import mops_quarterly_openapi_research_capture

    output_root, repository_root, _, readback, _, receipt = (
        _quarterly_terminal_binding_fixture(tmp_path, monkeypatch)
    )
    receipt["started_at_utc"] = "2026-10-03T08:00:30+00:00"
    with pytest.raises(binding.ResearchBindingError, match="clock_outside_parent_window"):
        binding._verify_weekly_child_bindings(output_root, repository_root, receipt)


def test_quarterly_internal_error_keeps_only_raw_process_pins(monkeypatch, tmp_path):
    repository_root = tmp_path
    run_root = repository_root / "output" / "mops_quarterly_openapi_research" / "internal-error"
    run_root.mkdir(parents=True)
    from data_module import mops_quarterly_openapi_research_capture

    error_terminal = {
        "schema_version": "mops-quarterly-openapi-research-terminal.v1",
        "run_id": "internal-error",
        "status": "collector_internal_error",
        "failed_at_utc": "2026-10-03T08:01:00+00:00",
        "eligibility": {"formal_pit_eligible": False},
    }
    (run_root / "collector_terminal.json").write_bytes(binding.canonical_json_bytes(error_terminal))
    stdout = b""
    stderr = b"collector failed before publishing a bound summary"
    stdout_path = tmp_path / "FA_Data/output/scheduled/v2_2_weekly_collection/controller_runs/internal/quarterly.stdout.json"
    stderr_path = stdout_path.with_name("quarterly.stderr.txt")
    stdout_path.parent.mkdir(parents=True)
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    item = controller._quarterly_child_binding(
        exit_code=2,
        summary=None,
        process_pins={
            "stdout": {"path": stdout_path.relative_to(tmp_path / "FA_Data/output").as_posix(), "sha256": hashlib.sha256(stdout).hexdigest(), "bytes": 0},
            "stderr": {"path": stderr_path.relative_to(tmp_path / "FA_Data/output").as_posix(), "sha256": hashlib.sha256(stderr).hexdigest(), "bytes": len(stderr)},
        },
        repository_root=repository_root,
    )
    assert item["status"] == "blocked"
    assert item["reason"] == "quarterly_child_stdout_invalid"
    assert "terminal" not in item
    assert error_terminal["status"] == "collector_internal_error"
    receipt = {
        "started_at_utc": "2026-10-03T07:59:00+00:00",
        "completed_at_utc": "2026-10-03T08:02:00+00:00",
        "core": {"exit_code": 0},
        "children": {"monthly_statement": {"status": "skipped"}, "quarterly_openapi": item},
    }
    result = binding._verify_weekly_child_bindings(
        tmp_path / "FA_Data/output", repository_root, receipt
    )
    assert result["quarterly_openapi"]["status"] == "blocked"
    assert result["quarterly_openapi"]["reason"] == "quarterly_child_stdout_invalid"
    assert result["quarterly_openapi"]["stdout_sha256"] == hashlib.sha256(stdout).hexdigest()


@pytest.mark.parametrize(
    ("changes", "expected_error"),
    [
        ({"process_exit_code": True}, "exit_code_must_be_int"),
        ({"reason": ""}, "blocked_reason_missing"),
        ({"timed_out": True}, "blocked_timeout_contradiction"),
        ({"timed_out": 1}, "timeout_flag_must_be_bool"),
    ],
)
def test_blocked_monthly_binding_requires_typed_terminal_diagnostics(tmp_path, changes, expected_error):
    _, repository_root, item, receipt, _ = _monthly_binding_fixture(
        tmp_path,
        declared_artifact_sha="sha256:" + "g" * 64,
    )
    item.update(changes)
    with pytest.raises(binding.ResearchBindingError, match=expected_error):
        binding._verify_weekly_child_bindings(
            tmp_path / "FA_Data" / "output",
            repository_root,
            receipt,
        )
