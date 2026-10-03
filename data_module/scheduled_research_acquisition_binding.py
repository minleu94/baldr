"""排程研究採集收據的唯讀綁定與重驗工具。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
from typing import Any, Mapping


WEEKLY_LOCATOR_SCHEMA = "scheduled-weekly-collection-locator.v1"
WEEKLY_RECEIPT_SCHEMA = "scheduled-weekly-collection-controller-receipt.v2"
WEEKLY_START_SCHEMA = "scheduled-weekly-collection-controller-start.v2"
WEEKLY_CONTROLLER_DIRECTORY = Path("scheduled") / "v2_2_weekly_collection" / "controller_runs"
WEEKLY_LOCATOR_RELATIVE_PATH = Path("scheduled") / "v2_2_weekly_collection" / "latest_status.json"
# core 僅作本機 SQLite 讀取與 sidecar append，設 30 秒硬上限；每週月營收 preset 固定六次、每次 30 秒且不重試。
WEEKLY_CORE_TIMEOUT_SECONDS = 30
WEEKLY_MONTHLY_QUERY_COUNT = 6
WEEKLY_MONTHLY_QUERY_TIMEOUT_SECONDS = 30
WEEKLY_MONTHLY_TIMEOUT_SECONDS = WEEKLY_MONTHLY_QUERY_COUNT * WEEKLY_MONTHLY_QUERY_TIMEOUT_SECONDS
# 季報 producer 的 900 秒是阻塞 HTTP 返回後才檢查的 elapsed gate；另留一次 30 秒 read 阻塞餘量。
WEEKLY_QUARTERLY_RUN_TIMEOUT_SECONDS = 900
WEEKLY_SINGLE_BLOCKING_MARGIN_SECONDS = 30
WEEKLY_QUARTERLY_TIMEOUT_SECONDS = WEEKLY_QUARTERLY_RUN_TIMEOUT_SECONDS + WEEKLY_SINGLE_BLOCKING_MARGIN_SECONDS
# 終端收據與 locator 原子發布的可見寬限；running 超時只標 blocked，不偽裝成已完成。
WEEKLY_CONTROLLER_PUBLICATION_GRACE_SECONDS = 30
WEEKLY_MAX_PENDING_SECONDS = (
    WEEKLY_CORE_TIMEOUT_SECONDS
    + WEEKLY_MONTHLY_TIMEOUT_SECONDS
    + WEEKLY_QUARTERLY_TIMEOUT_SECONDS
    + WEEKLY_CONTROLLER_PUBLICATION_GRACE_SECONDS
)
QUICK_CHILD_PUBLICATION_GRACE_SECONDS = 30
QUICK_CHILD_TIMEOUT_SECONDS = 90
QUICK_CHILD_TOTAL_GRACE_SECONDS = QUICK_CHILD_TIMEOUT_SECONDS + QUICK_CHILD_PUBLICATION_GRACE_SECONDS
MAX_RECEIPT_BYTES = 16 * 1024 * 1024
MAX_CHILD_BYTES = 64 * 1024 * 1024
WEEKLY_QUARTERLY_COMPLETED_STATES = frozenset(
    {"completed_observation_only", "completed_with_review_items"}
)
WEEKLY_QUARTERLY_PUBLISHED_FAILURE_STATES = frozenset(
    {
        "blocked_catalog_contract_or_transport",
        "run_elapsed_budget_exceeded",
        "request_elapsed_budget_exceeded",
        "completed_with_endpoint_failures",
        "blocked_incomplete_request_set",
    }
)


class ResearchBindingError(ValueError):
    """收據、來源或時間綁定不符合唯讀契約。"""


@dataclass(frozen=True)
class BoundJson:
    path: Path
    raw: bytes
    payload: dict[str, Any]
    sha256: str


def weekly_timing_budget_seconds() -> dict[str, int]:
    """回傳 controller 子程序上限及 pending 邊界的唯一計算依據。"""
    return {
        "core_process": WEEKLY_CORE_TIMEOUT_SECONDS,
        "monthly_statement_total": WEEKLY_MONTHLY_TIMEOUT_SECONDS,
        "monthly_query_count": WEEKLY_MONTHLY_QUERY_COUNT,
        "monthly_query_timeout": WEEKLY_MONTHLY_QUERY_TIMEOUT_SECONDS,
        "quarterly_run_gate": WEEKLY_QUARTERLY_RUN_TIMEOUT_SECONDS,
        "single_blocking_margin": WEEKLY_SINGLE_BLOCKING_MARGIN_SECONDS,
        "quarterly_process_total": WEEKLY_QUARTERLY_TIMEOUT_SECONDS,
        "controller_publication_grace": WEEKLY_CONTROLLER_PUBLICATION_GRACE_SECONDS,
        "running_pending_limit": WEEKLY_MAX_PENDING_SECONDS,
    }


def _validate_weekly_timing_budget(payload: Mapping[str, Any]) -> None:
    if payload.get("timing_budget_seconds") != weekly_timing_budget_seconds():
        raise ResearchBindingError("weekly_timing_budget_mismatch")


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parse_aware_utc(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ResearchBindingError(f"{field_name}_missing_or_invalid")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as exc:
        raise ResearchBindingError(f"{field_name}_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResearchBindingError(f"{field_name}_must_be_aware")
    return parsed.astimezone(timezone.utc)


def validate_weekly_quarterly_terminal(
    terminal: Mapping[str, Any],
    *,
    expected_run_id: str,
    expected_run_root: Path,
    process_exit_code: object,
    child_started_at: object,
) -> str:
    """驗證 weekly child 可綁定的正式季度 producer terminal schema。"""
    if terminal.get("schema_version") != "mops-quarterly-openapi-research-terminal.v1":
        raise ResearchBindingError("weekly_quarterly_terminal_schema_mismatch")
    if type(process_exit_code) is not int:
        raise ResearchBindingError("weekly_quarterly_exit_code_must_be_int")
    state = terminal.get("status")
    if state in WEEKLY_QUARTERLY_COMPLETED_STATES:
        expected_exit_code = 0
    elif state in WEEKLY_QUARTERLY_PUBLISHED_FAILURE_STATES:
        expected_exit_code = 2
    else:
        # collector_internal_error 使用不同的 failed_at_utc／nested eligibility
        # schema，且 CLI 不會產生可綁定本次 run_id 的 stdout summary。
        raise ResearchBindingError("weekly_quarterly_terminal_status_invalid")
    if process_exit_code != expected_exit_code:
        raise ResearchBindingError("weekly_quarterly_process_status_mismatch")
    if terminal.get("run_id") != expected_run_id:
        raise ResearchBindingError("weekly_quarterly_terminal_run_id_mismatch")
    declared_run_root = terminal.get("run_root")
    if not isinstance(declared_run_root, str) or not declared_run_root:
        raise ResearchBindingError("weekly_quarterly_terminal_run_root_missing")
    if not Path(declared_run_root).is_absolute() or Path(os.path.abspath(declared_run_root)) != Path(
        os.path.abspath(os.fspath(expected_run_root))
    ):
        raise ResearchBindingError("weekly_quarterly_terminal_run_root_mismatch")
    if terminal.get("candidate_available_at") is not None:
        raise ResearchBindingError("weekly_quarterly_qualification_boundary_changed")
    if (
        terminal.get("formal_pit_eligible") is not False
        or terminal.get("issuer_coverage_complete") is not False
    ):
        raise ResearchBindingError("weekly_quarterly_qualification_boundary_changed")
    readback = terminal.get("readback")
    if not isinstance(readback, Mapping):
        raise ResearchBindingError("weekly_quarterly_terminal_readback_missing")
    if (
        readback.get("run_id") != expected_run_id
        or readback.get("formal_pit_eligible") is not False
        or readback.get("issuer_coverage_complete") is not False
    ):
        raise ResearchBindingError("weekly_quarterly_terminal_readback_contract_changed")
    verification_completed = parse_aware_utc(
        terminal.get("verification_completed_at_utc"),
        field_name="weekly_quarterly_verification_completed_at",
    )
    artifact_materialized = parse_aware_utc(
        terminal.get("research_artifact_materialized_at_utc"),
        field_name="weekly_quarterly_artifact_materialized_at",
    )
    artifact_verified = parse_aware_utc(
        terminal.get("research_artifact_readback_verified_at_utc"),
        field_name="weekly_quarterly_artifact_readback_verified_at",
    )
    captured = parse_aware_utc(
        terminal.get("captured_at_utc"), field_name="weekly_quarterly_captured_at"
    )
    child_started = parse_aware_utc(
        child_started_at, field_name="weekly_quarterly_child_started_at"
    )
    if not (
        verification_completed == artifact_verified
        and child_started <= verification_completed <= artifact_materialized <= captured
    ):
        raise ResearchBindingError("weekly_quarterly_terminal_clock_order_invalid")
    return str(state)


def _assert_no_links(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    for candidate in reversed([*absolute.parents, absolute]):
        info = candidate.lstat()
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & reparse_flag):
            raise ResearchBindingError("receipt_path_contains_link")
        if candidate != absolute and not stat.S_ISDIR(info.st_mode):
            raise ResearchBindingError("receipt_parent_not_directory")
    return absolute


def _read_stable_bytes(path: Path, *, max_bytes: int) -> bytes:
    absolute = _assert_no_links(path)
    before = absolute.lstat()
    if not stat.S_ISREG(before.st_mode) or int(before.st_nlink) != 1:
        raise ResearchBindingError("receipt_file_not_regular_single_link")
    if int(before.st_size) > max_bytes:
        raise ResearchBindingError("receipt_file_too_large")
    with absolute.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if not stat.S_ISREG(opened.st_mode) or bool(getattr(opened, "st_file_attributes", 0) & reparse_flag):
            raise ResearchBindingError("receipt_file_open_identity_invalid")
        identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
        before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        if identity != before_identity or int(opened.st_nlink) != 1:
            raise ResearchBindingError("receipt_file_identity_changed")
        raw = handle.read(max_bytes + 1)
        after = os.fstat(handle.fileno())
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    if len(raw) > max_bytes or len(raw) != int(after.st_size) or identity != after_identity:
        raise ResearchBindingError("receipt_file_changed_or_too_large")
    return raw


def _strict_json_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ResearchBindingError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ResearchBindingError(f"non_finite_json_constant:{value}")


def read_bound_json(path: Path, *, max_bytes: int = MAX_RECEIPT_BYTES, expected_sha256: str | None = None) -> BoundJson:
    raw = _read_stable_bytes(path, max_bytes=max_bytes)
    actual_sha = sha256_bytes(raw)
    if expected_sha256 is not None and actual_sha != _normalize_sha256(expected_sha256):
        raise ResearchBindingError("receipt_sha256_mismatch")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_json_object_pairs, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ResearchBindingError("receipt_json_invalid") from exc
    if not isinstance(value, dict):
        raise ResearchBindingError("receipt_json_must_be_object")
    return BoundJson(path=Path(os.path.abspath(os.fspath(path))), raw=raw, payload=value, sha256=actual_sha)


def _normalize_sha256(value: object) -> str:
    if not isinstance(value, str):
        raise ResearchBindingError("sha256_missing_or_invalid")
    text = value.strip()
    if text.startswith("sha256:"):
        text = text[7:]
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ResearchBindingError("sha256_missing_or_invalid")
    return text


def resolve_output_relative_path(output_root: Path, value: object, *, must_exist: bool = True) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ResearchBindingError("artifact_relative_path_invalid")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} or ":" in part for part in pure.parts):
        raise ResearchBindingError("artifact_relative_path_invalid")
    root = Path(os.path.abspath(os.fspath(output_root)))
    candidate = root.joinpath(*pure.parts)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ResearchBindingError("artifact_path_escaped_output_root") from exc
    if must_exist:
        _assert_no_links(candidate)
    return candidate


def _controller_receipt_path(output_root: Path, relative_path: object) -> Path:
    candidate = resolve_output_relative_path(output_root, relative_path)
    try:
        relative = candidate.relative_to(Path(os.path.abspath(os.fspath(output_root))))
    except ValueError as exc:
        raise ResearchBindingError("weekly_receipt_path_outside_output_root") from exc
    parts = relative.parts
    if len(parts) != 5 or parts[:4] != (*WEEKLY_CONTROLLER_DIRECTORY.parts, parts[3]) or parts[4] not in {"start.json", "terminal.json"}:
        raise ResearchBindingError("weekly_receipt_path_not_controller_owned")
    run_id = parts[3]
    if not run_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in run_id):
        raise ResearchBindingError("weekly_receipt_run_id_path_invalid")
    return candidate


def _read_sidecar_record(sidecar_path: Path, *, collection_id: str) -> dict[str, Any]:
    _assert_no_links(sidecar_path)
    uri = Path(os.path.abspath(os.fspath(sidecar_path))).as_uri() + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            if int(connection.execute("PRAGMA query_only").fetchone()[0]) != 1:
                raise ResearchBindingError("weekly_sidecar_query_only_not_enabled")
            row = connection.execute(
                "SELECT collection_id, period_start, period_end, source_path, source_hash, status, payload_json, error_type, error_message, created_at FROM evidence_weekly_collections WHERE collection_id = ?",
                (collection_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise ResearchBindingError(f"weekly_sidecar_read_failed:{type(exc).__name__}") from exc
    if row is None:
        raise ResearchBindingError("weekly_sidecar_collection_missing")
    record = dict(row)
    try:
        record["payload_json"] = json.loads(str(record["payload_json"]))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ResearchBindingError("weekly_sidecar_payload_invalid") from exc
    return record


def _verify_core_binding(output_root: Path, receipt: Mapping[str, Any]) -> None:
    core = receipt.get("core")
    if not isinstance(core, Mapping):
        raise ResearchBindingError("weekly_core_binding_missing")
    stdout = core.get("stdout")
    if not isinstance(stdout, Mapping):
        raise ResearchBindingError("weekly_core_stdout_binding_missing")
    if core.get("timed_out") is True:
        if core.get("exit_code") is not None or core.get("collection_record") is not None or core.get("readback_status") != "blocked":
            raise ResearchBindingError("weekly_core_timeout_contract_invalid")
        if core.get("readback_reason") != "core_process_timeout":
            raise ResearchBindingError("weekly_core_timeout_reason_missing")
        _verify_output_bytes_pin(output_root, stdout, label="core_stdout")
        stderr = core.get("stderr")
        if not isinstance(stderr, Mapping):
            raise ResearchBindingError("weekly_core_stderr_binding_missing")
        _verify_output_bytes_pin(output_root, stderr, label="core_stderr")
        declared_source = receipt.get("source_db_path")
        declared_sidecar = receipt.get("sidecar_db_path")
        sidecar = core.get("sidecar")
        if not isinstance(declared_source, str) or not Path(declared_source).is_absolute():
            raise ResearchBindingError("weekly_source_db_invocation_path_invalid")
        if not isinstance(declared_sidecar, str) or not Path(declared_sidecar).is_absolute() or not isinstance(sidecar, Mapping):
            raise ResearchBindingError("weekly_sidecar_invocation_path_invalid")
        if isinstance(sidecar.get("path"), str):
            sidecar_path = resolve_output_relative_path(output_root, sidecar.get("path"), must_exist=False)
            if Path(os.path.abspath(declared_sidecar)) != sidecar_path:
                raise ResearchBindingError("weekly_sidecar_invocation_path_mismatch")
            _assert_no_links(sidecar_path if sidecar_path.exists() else sidecar_path.parent)
        elif sidecar.get("absolute_path") != declared_sidecar:
            raise ResearchBindingError("weekly_sidecar_invocation_path_mismatch")
        return
    if core.get("timed_out") is not False:
        raise ResearchBindingError("weekly_core_timeout_state_invalid")
    stdout_path = resolve_output_relative_path(output_root, stdout.get("path"))
    stdout_bound = read_bound_json(stdout_path, expected_sha256=str(stdout.get("sha256", "")))
    raw_record = stdout_bound.payload.get("collection_record")
    if not isinstance(raw_record, Mapping):
        raise ResearchBindingError("weekly_core_collection_record_missing")
    record = core.get("collection_record")
    if not isinstance(record, Mapping) or dict(raw_record) != dict(record):
        raise ResearchBindingError("weekly_core_stdout_record_mismatch")
    if type(core.get("exit_code")) is not int:
        raise ResearchBindingError("weekly_core_exit_code_must_be_int")
    if record.get("status") not in {"pending_human_review", "collection_failed"}:
        raise ResearchBindingError("weekly_core_status_invalid")
    if stdout_bound.payload.get("collection_status") != record.get("status"):
        raise ResearchBindingError("weekly_core_status_record_mismatch")
    if stdout_bound.payload.get("human_approval_required") is not True or stdout_bound.payload.get("automatic_revalidation") is not False or stdout_bound.payload.get("write_intent") is not False:
        raise ResearchBindingError("weekly_core_review_boundary_changed")
    source_db_path = receipt.get("source_db_path")
    if not isinstance(source_db_path, str) or not Path(source_db_path).is_absolute():
        raise ResearchBindingError("weekly_source_db_invocation_path_invalid")
    if stdout_bound.payload.get("source_db_path") != source_db_path or record.get("source_path") != source_db_path:
        raise ResearchBindingError("weekly_source_db_invocation_path_mismatch")
    if (record.get("status") == "pending_human_review") != (core.get("exit_code") == 0):
        raise ResearchBindingError("weekly_core_exit_status_contradiction")
    collection_id = record.get("collection_id")
    if not isinstance(collection_id, str) or not collection_id:
        raise ResearchBindingError("weekly_core_collection_id_invalid")
    sidecar = core.get("sidecar")
    if not isinstance(sidecar, Mapping):
        raise ResearchBindingError("weekly_core_sidecar_binding_missing")
    if isinstance(sidecar.get("path"), str):
        sidecar_path = resolve_output_relative_path(output_root, sidecar.get("path"))
        declared_sidecar = receipt.get("sidecar_db_path")
        if not isinstance(declared_sidecar, str) or Path(os.path.abspath(declared_sidecar)) != sidecar_path:
            raise ResearchBindingError("weekly_sidecar_invocation_path_mismatch")
    else:
        absolute_sidecar = sidecar.get("absolute_path")
        if not isinstance(absolute_sidecar, str) or not Path(absolute_sidecar).is_absolute():
            raise ResearchBindingError("weekly_sidecar_path_invalid")
        sidecar_path = _assert_no_links(Path(absolute_sidecar))
        if receipt.get("sidecar_db_path") != str(sidecar_path):
            raise ResearchBindingError("weekly_sidecar_invocation_path_mismatch")
    actual = _read_sidecar_record(sidecar_path, collection_id=collection_id)
    if actual != dict(record):
        raise ResearchBindingError("weekly_sidecar_record_mismatch")


def _verify_weekly_child_file(output_root: Path, item: Mapping[str, Any], *, label: str) -> BoundJson:
    path = resolve_output_relative_path(output_root, item.get("path"))
    bound = read_bound_json(path, expected_sha256=str(item.get("sha256", "")), max_bytes=MAX_CHILD_BYTES)
    schema = item.get("schema_version")
    if schema is not None and bound.payload.get("schema_version") != schema:
        raise ResearchBindingError(f"weekly_{label}_schema_mismatch")
    if item.get("run_id") is not None and bound.payload.get("run_id") != item.get("run_id"):
        raise ResearchBindingError(f"weekly_{label}_run_id_mismatch")
    return bound


def _verify_output_bytes_pin(output_root: Path, item: Mapping[str, Any], *, label: str) -> bytes:
    path = resolve_output_relative_path(output_root, item.get("path"))
    raw = _read_stable_bytes(path, max_bytes=MAX_CHILD_BYTES)
    if sha256_bytes(raw) != _normalize_sha256(item.get("sha256")) or len(raw) != item.get("bytes"):
        raise ResearchBindingError(f"weekly_{label}_bytes_pin_mismatch")
    return raw


def _resolve_known_child_path(repository_root: Path, value: object, *, lane: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ResearchBindingError(f"weekly_{lane}_path_missing")
    path = Path(value)
    if not path.is_absolute():
        raise ResearchBindingError(f"weekly_{lane}_path_must_be_absolute")
    root = Path(os.path.abspath(os.fspath(repository_root)))
    if lane == "monthly":
        allowed_root = root / "output" / "research" / "mops_statement_availability"
    elif lane == "quarterly":
        allowed_root = root / "output" / "mops_quarterly_openapi_research"
    else:
        raise ResearchBindingError("weekly_child_lane_invalid")
    absolute = Path(os.path.abspath(os.fspath(path)))
    try:
        relative = absolute.relative_to(allowed_root)
    except ValueError as exc:
        raise ResearchBindingError(f"weekly_{lane}_path_outside_producer_root") from exc
    if not relative.parts or any(part in {".", ".."} for part in relative.parts):
        raise ResearchBindingError(f"weekly_{lane}_path_invalid")
    _assert_no_links(absolute)
    return absolute


def _verify_absolute_child_pin(repository_root: Path, pin: Mapping[str, Any], *, lane: str, json_file: bool = True) -> BoundJson | bytes:
    path = _resolve_known_child_path(repository_root, pin.get("path"), lane=lane)
    expected_sha = _normalize_sha256(pin.get("sha256"))
    if json_file:
        return read_bound_json(path, expected_sha256=expected_sha, max_bytes=MAX_CHILD_BYTES)
    raw = _read_stable_bytes(path, max_bytes=MAX_CHILD_BYTES)
    if sha256_bytes(raw) != expected_sha:
        raise ResearchBindingError(f"weekly_{lane}_child_sha256_mismatch")
    return raw


def _verify_weekly_child_bindings(output_root: Path, repository_root: Path, receipt: Mapping[str, Any]) -> dict[str, Any]:
    children = receipt.get("children")
    if not isinstance(children, Mapping):
        raise ResearchBindingError("weekly_child_bindings_missing")
    result: dict[str, Any] = {}
    for name in ("monthly_statement", "quarterly_openapi"):
        item = children.get(name)
        if not isinstance(item, Mapping):
            raise ResearchBindingError(f"weekly_{name}_binding_missing")
        state = item.get("status")
        if state in {"skipped"}:
            result[name] = {"status": "not_requested", "reason": item.get("reason")}
            continue
        allowed_states = (
            {"captured_research", "official_no_data", "failed", "blocked"}
            if name == "monthly_statement"
            else {"completed_observation_only", "completed_with_review_items", "failed", "blocked"}
        )
        if state not in allowed_states:
            raise ResearchBindingError(f"weekly_{name}_status_invalid")
        stdout_pin = item.get("stdout")
        if state == "blocked":
            # 阻擋收據可能沒有 artifact pin；先驗原始輸出 bytes，保留阻擋原因，絕不升格為捕捉成功。
            if not isinstance(stdout_pin, Mapping):
                raise ResearchBindingError(f"weekly_{name}_stdout_pin_missing")
            stderr_pin = item.get("stderr")
            if not isinstance(stderr_pin, Mapping):
                raise ResearchBindingError(f"weekly_{name}_stderr_pin_missing")
            if type(stdout_pin.get("bytes")) is not int or type(stderr_pin.get("bytes")) is not int:
                raise ResearchBindingError(f"weekly_{name}_output_bytes_must_be_int")
            blocked_timed_out = item.get("timed_out", False)
            if type(blocked_timed_out) is not bool:
                raise ResearchBindingError(f"weekly_{name}_timeout_flag_must_be_bool")
            if blocked_timed_out:
                raise ResearchBindingError(f"weekly_{name}_blocked_timeout_contradiction")
            blocked_reason = item.get("reason")
            if not isinstance(blocked_reason, str) or not blocked_reason.strip():
                raise ResearchBindingError(f"weekly_{name}_blocked_reason_missing")
            process_exit = item.get("process_exit_code")
            if process_exit is not None and type(process_exit) is not int:
                raise ResearchBindingError(f"weekly_{name}_exit_code_must_be_int")
            stdout_raw = _verify_output_bytes_pin(output_root, stdout_pin, label=f"{name}_stdout")
            stderr_raw = _verify_output_bytes_pin(output_root, stderr_pin, label=f"{name}_stderr")
            result[name] = {
                "status": "blocked",
                "reason": blocked_reason,
                "process_exit_code": process_exit,
                "stdout_sha256": sha256_bytes(stdout_raw),
                "stderr_sha256": sha256_bytes(stderr_raw),
            }
            continue
        if state != "skipped":
            if not isinstance(stdout_pin, Mapping):
                raise ResearchBindingError(f"weekly_{name}_stdout_pin_missing")
            if item.get("timed_out") is True:
                _verify_output_bytes_pin(output_root, stdout_pin, label=f"{name}_stdout")
                stderr_pin = item.get("stderr")
                if not isinstance(stderr_pin, Mapping):
                    raise ResearchBindingError(f"weekly_{name}_stderr_pin_missing")
                _verify_output_bytes_pin(output_root, stderr_pin, label=f"{name}_stderr")
                if state != "failed" or item.get("process_exit_code") is not None:
                    raise ResearchBindingError(f"weekly_{name}_timeout_contract_invalid")
                result[name] = {"status": "failed", "reason": item.get("reason"), "timed_out": True}
                continue
            stdout_bound = _verify_weekly_child_file(output_root, stdout_pin, label=f"{name}_stdout")
            if name == "monthly_statement":
                artifact_pin = item.get("artifact")
                mapping_pin = item.get("mapping")
                if not isinstance(artifact_pin, Mapping) or not isinstance(mapping_pin, Mapping):
                    raise ResearchBindingError("weekly_monthly_child_artifact_pins_missing")
                stdout_artifact = stdout_bound.payload.get("artifact_path")
                stdout_mapping = stdout_bound.payload.get("mapping_path")
                if artifact_pin.get("path") != stdout_artifact or mapping_pin.get("path") != stdout_mapping:
                    raise ResearchBindingError("weekly_monthly_stdout_child_path_mismatch")
                if stdout_bound.payload.get("weekly_research_status") != item.get("raw_status") or stdout_bound.payload.get("status") != item.get("raw_status"):
                    raise ResearchBindingError("weekly_monthly_stdout_status_mismatch")
            else:
                stdout_run_root = stdout_bound.payload.get("run_root")
                stdout_run_id = stdout_bound.payload.get("run_id")
                if stdout_run_id != item.get("run_id") or stdout_run_root != item.get("run_root"):
                    raise ResearchBindingError("weekly_quarterly_stdout_identity_mismatch")
                if stdout_bound.payload.get("status") != item.get("raw_status"):
                    raise ResearchBindingError("weekly_quarterly_stdout_status_mismatch")
        process_exit = item.get("process_exit_code")
        timed_out = item.get("timed_out") is True
        if timed_out:
            if process_exit is not None or state != "failed":
                raise ResearchBindingError(f"weekly_{name}_timeout_contract_invalid")
            result[name] = {"status": "failed", "reason": item.get("reason"), "timed_out": True}
            continue
        elif type(process_exit) is not int:
            raise ResearchBindingError(f"weekly_{name}_exit_code_must_be_int")
        if name == "monthly_statement":
            status_file = item.get("weekly_status")
            if not isinstance(status_file, Mapping):
                raise ResearchBindingError("weekly_monthly_status_pin_missing")
            status_bound = _verify_absolute_child_pin(repository_root, status_file, lane="monthly")
            assert isinstance(status_bound, BoundJson)
            if status_bound.payload.get("schema_version") != "mops-weekly-research-capture-status.v1":
                raise ResearchBindingError("weekly_monthly_status_schema_mismatch")
            raw_status = status_bound.payload.get("status")
            if raw_status != item.get("raw_status"):
                raise ResearchBindingError("weekly_monthly_raw_status_mismatch")
            if state in {"captured_research", "official_no_data"} and raw_status != state:
                raise ResearchBindingError("weekly_monthly_status_value_mismatch")
            if state == "failed" and raw_status != "partial_failure":
                raise ResearchBindingError("weekly_monthly_failed_status_mismatch")
            if status_bound.payload.get("run_id") != item.get("run_id"):
                raise ResearchBindingError("weekly_monthly_run_id_mismatch")
            artifact_pin = item.get("artifact")
            if not isinstance(artifact_pin, Mapping):
                raise ResearchBindingError("weekly_monthly_artifact_pin_missing")
            artifact_path = _resolve_known_child_path(repository_root, artifact_pin.get("path"), lane="monthly")
            if artifact_path.parent != Path(str(item.get("run_root"))).resolve() or status_bound.path.parent != artifact_path.parent:
                raise ResearchBindingError("weekly_monthly_run_root_binding_mismatch")
            _validate_child_window(
                parent=receipt,
                child_started=status_bound.payload.get("collection_started_at_utc"),
                child_finished=status_bound.payload.get("collection_completed_at_utc"),
                lane="monthly",
            )
            for key in ("artifact", "mapping", "custody_receipt", "source_readback"):
                pin = item.get(key)
                if pin is None and key in {"custody_receipt", "source_readback"} and item.get("custody_status") == "not_enabled":
                    continue
                if not isinstance(pin, Mapping):
                    raise ResearchBindingError(f"weekly_monthly_{key}_pin_missing")
                bound = _verify_absolute_child_pin(repository_root, pin, lane="monthly", json_file=key != "mapping")
                if isinstance(bound, BoundJson) and pin.get("schema_version") is not None and bound.payload.get("schema_version") != pin.get("schema_version"):
                    raise ResearchBindingError(f"weekly_monthly_{key}_schema_mismatch")
            if item.get("custody_status") == "verified":
                from data_module.mops_success_response_custody import read_mops_success_response_custody
                verified_custody = read_mops_success_response_custody(
                    capture_root=artifact_path.parent / "raw_success_responses",
                    artifact_path=artifact_path,
                )
                if verified_custody.get("source_readback_status") != "verified":
                    raise ResearchBindingError("weekly_monthly_custody_semantic_readback_failed")
            if status_bound.payload.get("formal_oos_allowed") is not False or status_bound.payload.get("formal_credit_authorized") is not False:
                raise ResearchBindingError("weekly_monthly_qualification_boundary_changed")
            if state == "failed":
                result[name] = {"status": "failed", "reason": item.get("reason"), "run_id": status_bound.payload.get("run_id"), "status_sha256": status_bound.sha256}
            else:
                result[name] = {"status": "captured_verified" if state == "captured_research" else "official_no_data", "run_id": status_bound.payload.get("run_id"), "status_sha256": status_bound.sha256}
        else:
            terminal_pin = item.get("terminal")
            if not isinstance(terminal_pin, Mapping):
                raise ResearchBindingError("weekly_quarterly_terminal_pin_missing")
            terminal_path = _resolve_known_child_path(repository_root, terminal_pin.get("path"), lane="quarterly")
            terminal_bound = read_bound_json(terminal_path, expected_sha256=str(terminal_pin.get("sha256", "")), max_bytes=MAX_CHILD_BYTES)
            if item.get("run_id") != terminal_pin.get("run_id"):
                raise ResearchBindingError("weekly_quarterly_terminal_run_id_mismatch")
            if terminal_pin.get("schema_version") != "mops-quarterly-openapi-research-terminal.v1":
                raise ResearchBindingError("weekly_quarterly_terminal_schema_mismatch")
            run_root = terminal_path.parent
            declared_run_root = _resolve_known_child_path(repository_root, item.get("run_root"), lane="quarterly")
            if run_root != declared_run_root:
                raise ResearchBindingError("weekly_quarterly_terminal_run_root_mismatch")
            terminal_status = validate_weekly_quarterly_terminal(
                terminal_bound.payload,
                expected_run_id=str(item.get("run_id")),
                expected_run_root=declared_run_root,
                process_exit_code=process_exit,
                child_started_at=stdout_bound.payload.get("started_at_utc"),
            )
            if terminal_status != item.get("raw_status"):
                raise ResearchBindingError("weekly_quarterly_terminal_status_mismatch")
            if state in WEEKLY_QUARTERLY_COMPLETED_STATES:
                if state != terminal_status or item.get("reason") is not None:
                    raise ResearchBindingError("weekly_quarterly_completed_binding_mismatch")
            elif state == "failed":
                if (
                    terminal_status not in WEEKLY_QUARTERLY_PUBLISHED_FAILURE_STATES
                    or item.get("reason") != terminal_status
                ):
                    raise ResearchBindingError("weekly_quarterly_failure_reason_mismatch")
            else:
                raise ResearchBindingError("weekly_quarterly_child_state_invalid")
            _validate_child_window(
                parent=receipt,
                child_started=stdout_bound.payload.get("started_at_utc"),
                child_finished=terminal_bound.payload.get("captured_at_utc"),
                lane="quarterly",
            )
            from data_module.mops_quarterly_openapi_research_capture import verify_capture_run
            verified = verify_capture_run(run_root)
            if verified != terminal_bound.payload.get("readback"):
                raise ResearchBindingError("weekly_quarterly_terminal_readback_mismatch")
            if state in WEEKLY_QUARTERLY_COMPLETED_STATES:
                result[name] = {"status": "captured_with_review" if state == "completed_with_review_items" else "captured_verified", "run_id": terminal_pin.get("run_id"), "terminal_sha256": terminal_bound.sha256}
            else:
                result[name] = {"status": "failed", "reason": item.get("reason"), "producer_status": terminal_status, "run_id": terminal_pin.get("run_id"), "terminal_sha256": terminal_bound.sha256}
    return result


def _validate_child_window(
    *,
    parent: Mapping[str, Any],
    child_started: object,
    child_finished: object,
    lane: str,
) -> None:
    parent_started = parse_aware_utc(parent.get("started_at_utc"), field_name="weekly_started_at")
    parent_finished = parse_aware_utc(parent.get("completed_at_utc"), field_name="weekly_completed_at")
    started = parse_aware_utc(child_started, field_name=f"{lane}_started_at")
    finished = parse_aware_utc(child_finished, field_name=f"{lane}_completed_at")
    if not parent_started <= started <= finished <= parent_finished:
        raise ResearchBindingError(f"weekly_{lane}_clock_outside_parent_window")


def _receipt_status(receipt: Mapping[str, Any]) -> dict[str, Any]:
    core = receipt.get("core")
    if isinstance(core, Mapping) and core.get("timed_out") is True:
        if core.get("exit_code") is not None:
            raise ResearchBindingError("weekly_core_timeout_contract_invalid")
        return {"status": "failed", "reason": "weekly_core_process_timeout", "core_exit_code": None, "child_failures": []}
    core_exit = core.get("exit_code") if isinstance(core, Mapping) else None
    if type(core_exit) is not int:
        raise ResearchBindingError("weekly_core_exit_code_must_be_int")
    children = receipt.get("children")
    child_failures = []
    if isinstance(children, Mapping):
        child_failures = [name for name, item in children.items() if isinstance(item, Mapping) and item.get("status") in {"failed", "blocked"}]
    if core_exit != 0:
        return {"status": "failed", "reason": "weekly_core_exit_nonzero", "core_exit_code": core_exit, "child_failures": child_failures}
    if child_failures:
        return {"status": "partial", "reason": "weekly_research_child_failed", "core_exit_code": core_exit, "child_failures": child_failures}
    return {"status": "verified", "reason": "weekly_parent_and_children_bound", "core_exit_code": core_exit, "child_failures": []}


def verify_weekly_acquisition(
    output_root: Path,
    *,
    now: datetime,
    receipt_path: Path | None = None,
    expected_sha256: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """解析預設 locator 或精確外部 path+SHA；只重驗，不推測 lineage。"""
    if now.tzinfo is None or now.utcoffset() is None:
        return {"status": "blocked", "reason": "evaluation_clock_must_be_aware", "formal_credit": False}
    if (receipt_path is None) != (expected_sha256 is None):
        return {"status": "blocked", "reason": "external_receipt_path_sha_pair_incomplete", "formal_credit": False}
    root = Path(os.path.abspath(os.fspath(output_root)))
    repo = Path(os.path.abspath(os.fspath(repository_root or Path(__file__).resolve().parents[1])))
    try:
        if receipt_path is not None:
            resolved = Path(os.path.abspath(os.fspath(receipt_path)))
            try:
                relative = resolved.relative_to(root)
            except ValueError as exc:
                raise ResearchBindingError("external_weekly_receipt_outside_output_root") from exc
            relative_text = PurePosixPath(*relative.parts).as_posix()
            resolved = _controller_receipt_path(root, relative_text)
            receipt = read_bound_json(resolved, expected_sha256=expected_sha256)
            pointer = None
        else:
            locator_path = root / WEEKLY_LOCATOR_RELATIVE_PATH
            try:
                locator_bound = read_bound_json(locator_path)
            except FileNotFoundError:
                return {"status": "not_recorded", "reason": "weekly_locator_missing", "formal_credit": False}
            locator = locator_bound.payload
            if locator.get("schema_version") != WEEKLY_LOCATOR_SCHEMA:
                raise ResearchBindingError("weekly_locator_schema_mismatch")
            pointer = locator
            ref = locator.get("receipt")
            if not isinstance(ref, Mapping):
                raise ResearchBindingError("weekly_locator_receipt_missing")
            resolved = _controller_receipt_path(root, ref.get("path"))
            receipt = read_bound_json(resolved, expected_sha256=str(ref.get("sha256", "")))
            if receipt.payload.get("schema_version") != ref.get("schema_version"):
                raise ResearchBindingError("weekly_locator_receipt_schema_mismatch")
            if receipt.payload.get("run_id") != locator.get("run_id"):
                raise ResearchBindingError("weekly_locator_run_id_mismatch")
            if receipt.payload.get("state") != locator.get("state"):
                raise ResearchBindingError("weekly_locator_state_mismatch")
            if ref.get("path") != receipt.payload.get("receipt_relative_path"):
                raise ResearchBindingError("weekly_locator_path_mismatch")
        if pointer is not None and locator.get("state") == "terminal" and (
            receipt.payload.get("controller_clock_reason") is not None
            or receipt.payload.get("completed_at_utc") is None
        ):
            raise ResearchBindingError("weekly_controller_clock_invalid")
        if pointer is not None:
            updated = parse_aware_utc(locator.get("updated_at_utc"), field_name="weekly_locator_updated_at")
            if updated < parse_aware_utc(locator.get("started_at_utc"), field_name="weekly_locator_started_at") or updated > now.astimezone(timezone.utc):
                raise ResearchBindingError("weekly_locator_clock_invalid")
        payload = receipt.payload
        if payload.get("schema_version") not in {WEEKLY_START_SCHEMA, WEEKLY_RECEIPT_SCHEMA}:
            raise ResearchBindingError("weekly_parent_schema_mismatch")
        _validate_weekly_timing_budget(payload)
        if not isinstance(payload.get("run_id"), str) or not payload["run_id"]:
            raise ResearchBindingError("weekly_parent_run_id_missing")
        expected_relative = PurePosixPath(*receipt.path.relative_to(root).parts).as_posix()
        if payload.get("receipt_relative_path") != expected_relative:
            raise ResearchBindingError("weekly_parent_receipt_path_mismatch")
        declared_root = payload.get("output_root")
        if not isinstance(declared_root, str) or Path(os.path.abspath(declared_root)) != root:
            raise ResearchBindingError("weekly_parent_output_root_mismatch")
        started = parse_aware_utc(payload.get("started_at_utc"), field_name="weekly_started_at")
        now_utc = now.astimezone(timezone.utc)
        if started > now_utc:
            raise ResearchBindingError("weekly_parent_start_in_future")
        state = payload.get("state")
        if state == "running":
            age = now_utc - started
            status = "pending" if age <= timedelta(seconds=WEEKLY_MAX_PENDING_SECONDS) else "blocked"
            reason = "weekly_controller_running" if status == "pending" else "weekly_controller_terminal_timeout"
            return {"status": status, "reason": reason, "run_id": payload["run_id"], "receipt_path": str(receipt.path), "receipt_sha256": receipt.sha256, "age_seconds": int(age.total_seconds()), "pending_limit_seconds": WEEKLY_MAX_PENDING_SECONDS, "formal_credit": False}
        if state != "terminal" or payload.get("schema_version") != WEEKLY_RECEIPT_SCHEMA:
            raise ResearchBindingError("weekly_parent_state_invalid")
        if payload.get("controller_clock_reason") is not None:
            raise ResearchBindingError("weekly_controller_clock_invalid")
        clock_observation = payload.get("completion_clock_observation")
        if not isinstance(clock_observation, Mapping) or clock_observation.get("status") != "verified":
            raise ResearchBindingError("weekly_controller_clock_observation_invalid")
        observed_raw = clock_observation.get("observed_raw")
        if not isinstance(observed_raw, str):
            raise ResearchBindingError("weekly_controller_clock_observation_missing")
        observed_completed = parse_aware_utc(observed_raw, field_name="weekly_completion_clock_observed_raw")
        completed = parse_aware_utc(payload.get("completed_at_utc"), field_name="weekly_completed_at")
        if completed != observed_completed or completed < started or completed > now_utc:
            raise ResearchBindingError("weekly_parent_terminal_clock_invalid")
        if pointer is not None:
            pointer_started = parse_aware_utc(pointer.get("started_at_utc"), field_name="weekly_locator_started_at")
            pointer_updated = parse_aware_utc(pointer.get("updated_at_utc"), field_name="weekly_locator_updated_at")
            if pointer_started != started or pointer_updated != completed:
                raise ResearchBindingError("weekly_locator_terminal_clock_mismatch")
        _verify_core_binding(root, payload)
        children = _verify_weekly_child_bindings(root, repo, payload)
        receipt_status = _receipt_status(payload)
        core_payload = payload.get("core")
        collection_record = core_payload.get("collection_record") if isinstance(core_payload, Mapping) else None
        collection_id = collection_record.get("collection_id") if isinstance(collection_record, Mapping) else None
        core_status = collection_record.get("status") if isinstance(collection_record, Mapping) else None
        return {**receipt_status, "run_id": payload["run_id"], "receipt_path": str(receipt.path), "receipt_sha256": receipt.sha256, "started_at_utc": payload.get("started_at_utc"), "completed_at_utc": payload.get("completed_at_utc"), "collection_id": collection_id, "core_status": core_status, "children": children, "human_review_required": True, "formal_credit": False, "source_write_performed_by_audit": False, "locator_state": pointer.get("state") if isinstance(pointer, Mapping) else "explicit_external_pin"}
    except (OSError, ResearchBindingError, KeyError, TypeError, sqlite3.Error) as exc:
        return {"status": "blocked", "reason": str(exc) or type(exc).__name__, "error_type": type(exc).__name__, "formal_credit": False}


def quick_monthly_capture_status(
    *,
    quick_payload: Mapping[str, Any] | None,
    quick_binding: Mapping[str, Any],
    quick_status_path: Path,
    now: datetime,
) -> dict[str, Any]:
    """依已驗證 Quick 父收據判定月營收 child 等待、完成或失敗。"""
    if now.tzinfo is None or now.utcoffset() is None:
        return {"status": "blocked", "reason": "evaluation_clock_must_be_aware", "formal_credit": False}
    if quick_payload is None or quick_binding.get("binding_status") != "verified":
        return {"status": "blocked", "reason": "quick_parent_terminal_identity_not_verified", "formal_credit": False}
    declaration = quick_payload.get("monthly_revenue_research_capture")
    if not isinstance(declaration, Mapping):
        return {"status": "not_recorded", "reason": "quick_monthly_child_not_declared", "formal_credit": False}
    child_status = declaration.get("status")
    if child_status == "not_requested":
        return {"status": "not_recorded", "reason": "quick_monthly_child_not_requested", "formal_credit": False}
    if child_status == "skipped_core_failure":
        return {"status": "failed", "reason": "quick_core_failed_child_skipped", "formal_credit": False}
    if child_status not in {"pending_after_core_publication", "captured", "failed"}:
        return {"status": "blocked", "reason": "quick_monthly_child_status_invalid", "formal_credit": False}
    raw_path = declaration.get("result_receipt_path")
    if not isinstance(raw_path, str) or not raw_path:
        return {"status": "blocked", "reason": "quick_monthly_child_receipt_path_missing", "formal_credit": False}
    child_path = Path(raw_path)
    expected_parent = (quick_status_path.parent / "research_capture_receipts").resolve()
    try:
        resolved_child = child_path.resolve(strict=False)
        resolved_child.relative_to(expected_parent)
    except (OSError, ValueError):
        return {"status": "blocked", "reason": "quick_monthly_child_receipt_path_mismatch", "formal_credit": False}
    if child_path.suffix.lower() != ".json" or not child_path.name.startswith(str(quick_payload.get("run_id", "")) + "-"):
        return {"status": "blocked", "reason": "quick_monthly_child_receipt_identity_invalid", "formal_credit": False}
    if child_status == "failed":
        return {"status": "failed", "reason": "quick_monthly_child_declared_failed", "formal_credit": False}
    if not child_path.exists():
        try:
            completed = parse_aware_utc(quick_payload.get("completed_at"), field_name="quick_completed_at")
        except ResearchBindingError as exc:
            return {"status": "blocked", "reason": str(exc), "formal_credit": False}
        now_utc = now.astimezone(timezone.utc)
        if completed > now_utc:
            return {"status": "blocked", "reason": "quick_completed_at_in_future", "formal_credit": False}
        age = now_utc - completed
        if age <= timedelta(seconds=QUICK_CHILD_TOTAL_GRACE_SECONDS):
            return {"status": "pending", "reason": "quick_monthly_child_publication_grace", "age_seconds": int(age.total_seconds()), "pending_limit_seconds": QUICK_CHILD_TOTAL_GRACE_SECONDS, "formal_credit": False}
        return {"status": "blocked", "reason": "quick_monthly_child_receipt_missing_after_grace", "age_seconds": int(age.total_seconds()), "pending_limit_seconds": QUICK_CHILD_TOTAL_GRACE_SECONDS, "formal_credit": False}
    return {"status": "receipt_present", "reason": "quick_monthly_child_receipt_available_for_script_layer_audit", "child_path": str(child_path), "formal_credit": False}
