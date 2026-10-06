"""以 create-only 父收據綁定既有週收集與研究子程序。"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import uuid
from typing import Any, Iterator, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_module import scheduled_research_acquisition_binding as binding


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _completion_clock_record(now: Any, *, started: datetime) -> tuple[str | None, str | None, dict[str, Any]]:
    """保留實際完成時鐘；未知或無效時絕不以開始時間補值。"""
    try:
        observed = now()
    except Exception as exc:
        reason = "controller_completion_clock_unavailable"
        return None, reason, {
            "status": "unknown",
            "observed_type": "unavailable",
            "observed_raw": None,
            "reason": reason,
            "error_type": type(exc).__name__,
        }
    if not isinstance(observed, datetime):
        reason = "controller_completion_clock_invalid"
        return None, reason, {
            "status": "unknown",
            "observed_type": type(observed).__name__,
            "observed_raw": None,
            "reason": "clock_value_not_datetime",
        }
    raw_value = observed.isoformat()
    if observed.tzinfo is None or observed.utcoffset() is None:
        reason = "controller_completion_clock_invalid"
        return None, reason, {
            "status": "unknown",
            "observed_type": "datetime",
            "observed_raw": raw_value,
            "reason": "clock_timezone_missing",
        }
    completed = observed.astimezone(timezone.utc)
    if completed < started.astimezone(timezone.utc):
        reason = "controller_completion_clock_invalid"
        return None, reason, {
            "status": "unknown",
            "observed_type": "datetime",
            "observed_raw": raw_value,
            "reason": "clock_before_controller_start",
        }
    return completed.isoformat(), None, {
        "status": "verified",
        "observed_type": "datetime",
        "observed_raw": raw_value,
        "reason": None,
    }


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return binding.canonical_json_bytes(payload)


def _strict_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=binding._strict_json_object_pairs, parse_constant=binding._reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise binding.ResearchBindingError("child_stdout_json_invalid") from exc
    if not isinstance(value, dict):
        raise binding.ResearchBindingError("child_stdout_must_be_object")
    return value


def _relative_to_root(root: Path, path: Path) -> str:
    absolute_root = Path(os.path.abspath(os.fspath(root)))
    absolute_path = Path(os.path.abspath(os.fspath(path)))
    try:
        return PurePosixPath(*absolute_path.relative_to(absolute_root).parts).as_posix()
    except ValueError as exc:
        raise binding.ResearchBindingError("controller_artifact_outside_output_root") from exc


def _safe_mkdir(root: Path, path: Path) -> None:
    root_abs = Path(os.path.abspath(os.fspath(root)))
    path_abs = Path(os.path.abspath(os.fspath(path)))
    try:
        relative = path_abs.relative_to(root_abs)
    except ValueError as exc:
        raise binding.ResearchBindingError("controller_run_path_outside_output_root") from exc
    current = root_abs
    if not current.exists():
        current.mkdir(parents=True, exist_ok=True)
    binding._assert_no_links(current)
    for part in relative.parts:
        current = current / part
        try:
            current.mkdir(exist_ok=False)
        except FileExistsError:
            info = current.lstat()
            if not current.is_dir() or current.is_symlink() or getattr(info, "st_file_attributes", 0) & getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                raise binding.ResearchBindingError("controller_output_directory_not_regular")


def _create_only(path: Path, raw: bytes) -> None:
    binding._assert_no_links(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def _locator_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            lock_file = getattr(fcntl, "flock")
            lock_ex = getattr(fcntl, "LOCK_EX")
            lock_un = getattr(fcntl, "LOCK_UN")
            lock_file(handle.fileno(), lock_ex)
            try:
                yield
            finally:
                lock_file(handle.fileno(), lock_un)


def _publish_locator(
    output_root: Path,
    *,
    run_id: str,
    state: str,
    receipt_relative_path: str,
    receipt_raw: bytes,
    receipt_schema: str,
    started_at_utc: str,
    updated_at_utc: str,
    allow_replace_other_run: bool,
) -> bool:
    locator_path = output_root / binding.WEEKLY_LOCATOR_RELATIVE_PATH
    locator_path.parent.mkdir(parents=True, exist_ok=True)
    binding._assert_no_links(locator_path.parent)
    lock_path = locator_path.parent / ".latest_status.lock"
    with _locator_lock(lock_path):
        current: dict[str, Any] | None = None
        if locator_path.exists():
            current_bound = binding.read_bound_json(locator_path)
            current = current_bound.payload
        if not allow_replace_other_run and (current is None or current.get("run_id") != run_id):
            return False
        if allow_replace_other_run and current is not None:
            try:
                previous_started = binding.parse_aware_utc(current.get("started_at_utc"), field_name="locator_started_at")
                current_started = binding.parse_aware_utc(started_at_utc, field_name="new_started_at")
            except binding.ResearchBindingError:
                raise binding.ResearchBindingError("existing_weekly_locator_invalid")
            if previous_started > current_started:
                return False
        payload = {
            "schema_version": binding.WEEKLY_LOCATOR_SCHEMA,
            "state": state,
            "run_id": run_id,
            "receipt": {
                "path": receipt_relative_path,
                "sha256": _sha(receipt_raw),
                "schema_version": receipt_schema,
            },
            "started_at_utc": started_at_utc,
            "updated_at_utc": updated_at_utc,
        }
        temp = locator_path.with_name(f".{locator_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            _create_only(temp, _json_bytes(payload))
            os.replace(temp, locator_path)
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass
        return True


def _capture_process(
    *,
    command: list[str],
    repo_root: Path,
    output_root: Path,
    run_root: Path,
    label: str,
    runner: Any = subprocess.run,
    timeout_seconds: int | None = None,
) -> tuple[int | None, dict[str, Any] | None, dict[str, Any], bool]:
    timed_out = False
    spawn_error: str | None = None
    try:
        completed = runner(command, cwd=repo_root, capture_output=True, check=False, timeout=timeout_seconds)
        returncode: int | None = int(completed.returncode)
        stdout = bytes(completed.stdout or b"")
        stderr = bytes(completed.stderr or b"")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = None
        stdout_value = exc.stdout or b""
        stderr_value = exc.stderr or b""
        stdout = stdout_value.encode("utf-8", errors="replace") if isinstance(stdout_value, str) else bytes(stdout_value)
        stderr = stderr_value.encode("utf-8", errors="replace") if isinstance(stderr_value, str) else bytes(stderr_value)
    except OSError as exc:
        returncode = None
        stdout = b""
        stderr = f"{type(exc).__name__}:{exc}".encode("utf-8", errors="backslashreplace")
        spawn_error = f"{type(exc).__name__}:{exc}"
    stdout_path = run_root / f"{label}.stdout.json"
    stderr_path = run_root / f"{label}.stderr.txt"
    _create_only(stdout_path, stdout)
    _create_only(stderr_path, stderr)
    stdout_pin = {"path": _relative_to_root(output_root, stdout_path), "sha256": _sha(stdout), "bytes": len(stdout)}
    stderr_pin = {"path": _relative_to_root(output_root, stderr_path), "sha256": _sha(stderr), "bytes": len(stderr)}
    try:
        parsed = _strict_json(stdout) if stdout.strip() else None
    except binding.ResearchBindingError:
        parsed = None
    pins: dict[str, Any] = {"stdout": stdout_pin, "stderr": stderr_pin}
    if spawn_error is not None:
        pins["process_error"] = spawn_error
    return returncode, parsed, pins, timed_out


def _absolute_pin(path_value: object, *, repository_root: Path, lane: str, max_bytes: int, json_file: bool = True) -> dict[str, Any]:
    if not isinstance(path_value, str) or not path_value:
        raise binding.ResearchBindingError(f"{lane}_path_missing")
    path = binding._resolve_known_child_path(repository_root, path_value, lane=lane)
    raw = binding._read_stable_bytes(path, max_bytes=max_bytes)
    pin: dict[str, Any] = {"path": str(path), "sha256": _sha(raw), "bytes": len(raw)}
    if json_file:
        payload = _strict_json(raw)
        pin["schema_version"] = payload.get("schema_version")
        pin["run_id"] = payload.get("run_id")
    return pin


def _monthly_child_binding(
    *,
    exit_code: int | None,
    summary: dict[str, Any] | None,
    process_pins: dict[str, Any],
    repository_root: Path,
    timed_out: bool = False,
) -> dict[str, Any]:
    item: dict[str, Any] = {"status": "blocked", "stdout": process_pins["stdout"], "stderr": process_pins["stderr"]}
    if timed_out:
        item.update({"status": "failed", "reason": "monthly_child_process_timeout", "process_exit_code": None, "timed_out": True})
        return item
    if summary is None:
        item.update({"reason": "monthly_child_stdout_invalid", "process_exit_code": exit_code})
        return item
    artifact_path = summary.get("artifact_path")
    try:
        artifact = binding._resolve_known_child_path(repository_root, artifact_path, lane="monthly")
        run_root = artifact.parent
        status_path = run_root / "weekly_research_status.json"
        status_bound = binding.read_bound_json(status_path, max_bytes=binding.MAX_RECEIPT_BYTES)
        status = status_bound.payload
        if status.get("schema_version") != "mops-weekly-research-capture-status.v1" or status.get("run_id") != run_root.name:
            raise binding.ResearchBindingError("monthly_weekly_status_identity_invalid")
        if status.get("artifact_path") != str(artifact) or summary.get("artifact_path") != str(artifact):
            raise binding.ResearchBindingError("monthly_artifact_path_mismatch")
        artifact_raw = binding._read_stable_bytes(artifact, max_bytes=binding.MAX_CHILD_BYTES)
        artifact_sha = _sha(artifact_raw)
        if binding._normalize_sha256(status.get("artifact_sha256")) != binding._normalize_sha256(artifact_sha):
            raise binding.ResearchBindingError("monthly_artifact_sha256_mismatch")
        mapping = binding._resolve_known_child_path(repository_root, summary.get("mapping_path"), lane="monthly")
        mapping_raw = binding._read_stable_bytes(mapping, max_bytes=binding.MAX_CHILD_BYTES)
        custody_path = status.get("custody_receipt_path")
        custody_receipt: dict[str, Any] | None = None
        source_readback: dict[str, Any] | None = None
        custody_status = str(status.get("source_readback_status", "not_enabled"))
        if custody_status == "verified":
            capture_root = artifact.parent / "raw_success_responses"
            from data_module.mops_success_response_custody import (
                MOPS_SUCCESS_CUSTODY_READBACK,
                MOPS_SUCCESS_CUSTODY_RECEIPT,
                read_mops_success_response_custody,
            )
            verified = read_mops_success_response_custody(capture_root=capture_root, artifact_path=artifact)
            if verified.get("source_readback_status") != "verified":
                raise binding.ResearchBindingError("monthly_custody_readback_not_verified")
            custody_receipt = _absolute_pin(str(capture_root / MOPS_SUCCESS_CUSTODY_RECEIPT), repository_root=repository_root, lane="monthly", max_bytes=binding.MAX_RECEIPT_BYTES)
            source_readback = _absolute_pin(str(capture_root / MOPS_SUCCESS_CUSTODY_READBACK), repository_root=repository_root, lane="monthly", max_bytes=binding.MAX_RECEIPT_BYTES)
            if custody_path != custody_receipt["path"]:
                raise binding.ResearchBindingError("monthly_custody_path_mismatch")
        elif custody_status != "not_enabled":
            raise binding.ResearchBindingError("monthly_custody_status_invalid")
        weekly_status_pin = {"path": str(status_path), "sha256": status_bound.sha256, "bytes": len(status_bound.raw), "schema_version": status.get("schema_version"), "run_id": status.get("run_id")}
        state = status.get("status")
        raw_status = state
        allowed = {"captured_research", "official_no_data"}
        if state not in allowed:
            state = "failed" if exit_code != 0 or status.get("status") == "partial_failure" else "blocked"
        elif exit_code != 0 or summary.get("weekly_research_status") != state:
            state = "blocked"
        item.update({
            "status": state,
            "raw_status": raw_status,
            "reason": None if state in allowed else "monthly_child_partial_or_process_failure",
            "process_exit_code": exit_code,
            "weekly_status": weekly_status_pin,
            "artifact": _absolute_pin(str(artifact), repository_root=repository_root, lane="monthly", max_bytes=binding.MAX_CHILD_BYTES),
            "mapping": {"path": str(mapping), "sha256": _sha(mapping_raw), "bytes": len(mapping_raw)},
            "custody_receipt": custody_receipt,
            "source_readback": source_readback,
            "custody_status": custody_status,
            "run_id": status.get("run_id"),
            "run_root": str(run_root),
        })
    except (OSError, ValueError, TypeError, KeyError) as exc:
        item.update({"reason": f"{type(exc).__name__}:{exc}", "process_exit_code": exit_code})
    return item


def _quarterly_child_binding(
    *,
    exit_code: int | None,
    summary: dict[str, Any] | None,
    process_pins: dict[str, Any],
    repository_root: Path,
    timed_out: bool = False,
) -> dict[str, Any]:
    item: dict[str, Any] = {"status": "blocked", "stdout": process_pins["stdout"], "stderr": process_pins["stderr"]}
    if timed_out:
        item.update({"status": "failed", "reason": "quarterly_child_process_timeout", "process_exit_code": None, "timed_out": True})
        return item
    if summary is None:
        item.update({"reason": "quarterly_child_stdout_invalid", "process_exit_code": exit_code})
        return item
    try:
        summary_run_id = summary.get("run_id")
        if not isinstance(summary_run_id, str) or not summary_run_id:
            raise binding.ResearchBindingError("quarterly_stdout_run_id_missing")
        run_root = binding._resolve_known_child_path(repository_root, summary.get("run_root"), lane="quarterly")
        terminal_path = run_root / "collector_terminal.json"
        terminal_bound = binding.read_bound_json(terminal_path, max_bytes=binding.MAX_CHILD_BYTES)
        terminal = terminal_bound.payload
        child_started = binding.parse_aware_utc(
            summary.get("started_at_utc"), field_name="weekly_quarterly_stdout_started_at"
        )
        state = binding.validate_weekly_quarterly_terminal(
            terminal,
            expected_run_id=summary_run_id,
            expected_run_root=run_root,
            process_exit_code=exit_code,
            child_started_at=child_started.isoformat(),
        )
        if summary.get("status") != state:
            raise binding.ResearchBindingError("quarterly_stdout_status_mismatch")
        if Path(os.path.abspath(str(summary.get("run_root")))) != run_root:
            raise binding.ResearchBindingError("quarterly_stdout_run_root_mismatch")
        if summary.get("terminal") != terminal:
            raise binding.ResearchBindingError("quarterly_stdout_terminal_mismatch")
        child_completed = binding.parse_aware_utc(
            terminal.get("captured_at_utc"), field_name="weekly_quarterly_captured_at"
        )
        if child_completed < child_started:
            raise binding.ResearchBindingError("weekly_quarterly_child_clock_order_invalid")
        from data_module.mops_quarterly_openapi_research_capture import verify_capture_run
        verified = verify_capture_run(run_root)
        if verified != terminal.get("readback"):
            raise binding.ResearchBindingError("quarterly_terminal_readback_mismatch")
        child_status = state if state in binding.WEEKLY_QUARTERLY_COMPLETED_STATES else "failed"
        item.update({
            "status": child_status,
            "raw_status": state,
            "reason": None if child_status.startswith("completed_") else str(state or "quarterly_process_failed"),
            "process_exit_code": exit_code,
            "terminal": {"path": str(terminal_path), "sha256": terminal_bound.sha256, "bytes": len(terminal_bound.raw), "schema_version": terminal.get("schema_version"), "run_id": terminal.get("run_id")},
            "run_id": terminal.get("run_id"),
            "run_root": str(run_root),
        })
    except (OSError, ValueError, TypeError, KeyError) as exc:
        item.update({"reason": f"{type(exc).__name__}:{exc}", "process_exit_code": exit_code})
    return item


def _read_sidecar_row(sidecar_path: Path, collection_id: str) -> dict[str, Any]:
    return binding._read_sidecar_record(sidecar_path, collection_id=collection_id)


def run_controller(
    *,
    source_db_path: Path,
    sidecar_db_path: Path,
    output_root: Path,
    repository_root: Path = REPO_ROOT,
    period_end: str | None = None,
    runner: Any = subprocess.run,
    now: Any = _utc_now,
    environ: Mapping[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    output_root = Path(os.path.abspath(os.fspath(output_root)))
    repository_root = Path(os.path.abspath(os.fspath(repository_root)))
    source_db_path = Path(os.path.abspath(os.fspath(source_db_path)))
    sidecar_db_path = Path(os.path.abspath(os.fspath(sidecar_db_path)))
    run_id = "weekly_" + uuid.uuid4().hex
    relative_run = binding.WEEKLY_CONTROLLER_DIRECTORY / run_id
    run_root = output_root / relative_run
    _safe_mkdir(output_root, run_root)
    started = now()
    if started.tzinfo is None or started.utcoffset() is None:
        raise binding.ResearchBindingError("controller_clock_must_be_aware")
    started_text = started.astimezone(timezone.utc).isoformat()
    start_payload = {
        "schema_version": binding.WEEKLY_START_SCHEMA,
        "state": "running",
        "run_id": run_id,
        "receipt_relative_path": (relative_run / "start.json").as_posix(),
        "started_at_utc": started_text,
        "timing_budget_seconds": binding.weekly_timing_budget_seconds(),
        "output_root": str(output_root),
        "source_db_path": str(source_db_path),
        "sidecar_db_path": str(sidecar_db_path),
        "formal_database_write_performed_by_controller": False,
    }
    start_raw = _json_bytes(start_payload)
    start_path = run_root / "start.json"
    _create_only(start_path, start_raw)
    _publish_locator(
        output_root,
        run_id=run_id,
        state="running",
        receipt_relative_path=start_payload["receipt_relative_path"],
        receipt_raw=start_raw,
        receipt_schema=binding.WEEKLY_START_SCHEMA,
        started_at_utc=started_text,
        updated_at_utc=started_text,
        allow_replace_other_run=True,
    )

    python = sys.executable
    core_command = [python, str(repository_root / "scripts" / "collect_v2_2_weekly_evidence.py"), "--source-db-path", str(source_db_path), "--sidecar-db-path", str(sidecar_db_path), "--output-root", str(output_root), "--json-output"]
    if period_end is not None:
        core_command.extend(["--period-end", period_end])
    core_exit, core_payload, core_pins, core_timed_out = _capture_process(
        command=core_command,
        repo_root=repository_root,
        output_root=output_root,
        run_root=run_root,
        label="core",
        runner=runner,
        timeout_seconds=binding.WEEKLY_CORE_TIMEOUT_SECONDS,
    )
    try:
        sidecar_pin: dict[str, str] = {"path": _relative_to_root(output_root, sidecar_db_path)}
    except binding.ResearchBindingError:
        sidecar_pin = {"absolute_path": str(sidecar_db_path)}
    core_binding: dict[str, Any] = {
        "exit_code": core_exit,
        "timed_out": core_timed_out,
        "stdout": core_pins["stdout"],
        "stderr": core_pins["stderr"],
        "collection_record": None,
        "sidecar": sidecar_pin,
        "readback_status": "blocked",
    }
    record = core_payload.get("collection_record") if isinstance(core_payload, Mapping) else None
    if core_timed_out:
        core_binding["readback_reason"] = "core_process_timeout"
    elif isinstance(record, Mapping):
        core_binding["collection_record"] = dict(record)
        try:
            sidecar_path = (
                binding.resolve_output_relative_path(output_root, core_binding["sidecar"]["path"])
                if "path" in core_binding["sidecar"]
                else Path(core_binding["sidecar"]["absolute_path"])
            )
            sidecar_record = _read_sidecar_row(sidecar_path, str(record.get("collection_id", "")))
            if sidecar_record != dict(record):
                raise binding.ResearchBindingError("weekly_sidecar_record_mismatch")
            core_binding["readback_status"] = "verified"
        except (OSError, ValueError, TypeError, KeyError) as exc:
            core_binding["readback_reason"] = f"{type(exc).__name__}:{exc}"
    else:
        core_binding["readback_reason"] = "core_stdout_collection_record_missing"

    env = dict(os.environ if environ is None else environ)
    children: dict[str, Any] = {}
    if core_exit != 0:
        children["monthly_statement"] = {"status": "skipped", "reason": "core_exit_nonzero"}
        children["quarterly_openapi"] = {"status": "skipped", "reason": "core_exit_nonzero"}
    else:
        if env.get("BALDR_ENABLE_MOPS_STATEMENT_CUSTODY", "1").strip() != "0":
            monthly_command = [python, str(repository_root / "scripts" / "fetch_mops_statement_availability.py"), "--last-complete-taipei-7-days"]
            monthly_exit, monthly_summary, monthly_pins, monthly_timed_out = _capture_process(command=monthly_command, repo_root=repository_root, output_root=output_root, run_root=run_root, label="monthly_statement", runner=runner, timeout_seconds=binding.WEEKLY_MONTHLY_TIMEOUT_SECONDS)
            children["monthly_statement"] = _monthly_child_binding(exit_code=monthly_exit, summary=monthly_summary, process_pins=monthly_pins, repository_root=repository_root, timed_out=monthly_timed_out)
        else:
            children["monthly_statement"] = {"status": "skipped", "reason": "BALDR_ENABLE_MOPS_STATEMENT_CUSTODY=0"}
        if env.get("BALDR_ENABLE_MOPS_QUARTERLY_OPENAPI_RESEARCH", "1").strip() != "0":
            quarterly_command = [python, str(repository_root / "scripts" / "capture_mops_quarterly_openapi_research.py"), "--capture"]
            quarterly_exit, quarterly_summary, quarterly_pins, quarterly_timed_out = _capture_process(command=quarterly_command, repo_root=repository_root, output_root=output_root, run_root=run_root, label="quarterly_openapi", runner=runner, timeout_seconds=binding.WEEKLY_QUARTERLY_TIMEOUT_SECONDS)
            children["quarterly_openapi"] = _quarterly_child_binding(exit_code=quarterly_exit, summary=quarterly_summary, process_pins=quarterly_pins, repository_root=repository_root, timed_out=quarterly_timed_out)
        else:
            children["quarterly_openapi"] = {"status": "skipped", "reason": "BALDR_ENABLE_MOPS_QUARTERLY_OPENAPI_RESEARCH=0"}

    completed_text, clock_reason, clock_observation = _completion_clock_record(now, started=started)
    terminal = {
        "schema_version": binding.WEEKLY_RECEIPT_SCHEMA,
        "state": "terminal",
        "run_id": run_id,
        "receipt_relative_path": (relative_run / "terminal.json").as_posix(),
        "output_root": str(output_root),
        "source_db_path": str(source_db_path),
        "sidecar_db_path": str(sidecar_db_path),
        "started_at_utc": started_text,
        "completed_at_utc": completed_text,
        "completion_clock_observation": clock_observation,
        "timing_budget_seconds": binding.weekly_timing_budget_seconds(),
        "core": core_binding,
        "children": children,
        "controller_clock_reason": clock_reason,
        "human_review_required": True,
        "formal_pit_eligible": False,
        "candidate_available_at": None,
        "formal_database_write_performed_by_controller": False,
    }
    terminal_raw = _json_bytes(terminal)
    terminal_path = run_root / "terminal.json"
    _create_only(terminal_path, terminal_raw)
    terminal_published = _publish_locator(
        output_root,
        run_id=run_id,
        state="terminal",
        receipt_relative_path=terminal["receipt_relative_path"],
        receipt_raw=terminal_raw,
        receipt_schema=binding.WEEKLY_RECEIPT_SCHEMA,
        started_at_utc=started_text,
        updated_at_utc=terminal["completed_at_utc"],
        allow_replace_other_run=False,
    )
    result = {
        "schema_version": "scheduled-weekly-collection-controller-result.v1",
        "status": "terminal" if terminal_published else "terminal_not_latest",
        "run_id": run_id,
        "core_exit_code": core_exit,
        "receipt_path": str(terminal_path),
        "receipt_sha256": _sha(terminal_raw),
        "locator_published": terminal_published,
        "human_review_required": True,
        "formal_credit": False,
    }
    effective_exit = core_exit if type(core_exit) is int else 2
    return effective_exit, result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db-path", required=True, type=Path)
    parser.add_argument("--sidecar-db-path", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--period-end")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    try:
        exit_code, result = run_controller(source_db_path=args.source_db_path, sidecar_db_path=args.sidecar_db_path, output_root=args.output_root, period_end=args.period_end)
    except (OSError, ValueError, RuntimeError) as exc:
        result = {"schema_version": "scheduled-weekly-collection-controller-result.v1", "status": "blocked", "reason": f"{type(exc).__name__}:{exc}", "formal_credit": False}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return exit_code


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass


if __name__ == "__main__":
    raise SystemExit(main())
