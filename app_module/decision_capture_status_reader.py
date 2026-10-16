"""唯讀核對既有決策擷取終態；不執行排程、producer 或資料庫查詢。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, DecimalException
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app_module.decision_snapshot_diagnostics import summarize_snapshot_diagnostics
from app_module.recommendation_portfolio_calendar_artifact_v1 import (
    _canonical_path, _read_exact_file, _validate_json_depth,
)
from app_module.sqlite_read_only import ReadOperationCancelled, check_read_cancelled

_MAX_JSON = 1024 * 1024
_MAX_OUTPUT = 64 * 1024
_RUN_ID = re.compile(r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{12}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CODE = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_TAIPEI = ZoneInfo("Asia/Taipei")
_TERMINAL_STATUSES = frozenset({
    "passed", "failed", "degraded", "skipped_non_trading_day", "degraded_calendar_unknown",
    "blocked_reservation_not_acquired", "blocked_reservation_error", "blocked_reservation_timeout",
    "blocked_reservation_acquire_guard", "failed_reservation_release",
})


@dataclass(frozen=True)
class DecisionCaptureStage:
    stage: str
    state: str
    elapsed_ms: int
    error_type: str = ""


@dataclass(frozen=True)
class DecisionCaptureRunStatus:
    status_path: Path
    read_state: str
    diagnostic: str = ""
    raw_status: str = "unknown"
    run_id: str = ""
    decision_date: str = ""
    completed_at: str = ""
    receipt_path: str = ""
    receipt_sha256: str = ""
    snapshot_status: str = "unknown"
    snapshot_saved: bool | None = None
    snapshot_duplicate: bool | None = None
    snapshot_execution_status: str = "not_started"
    capture_mode: str = ""
    temporal_status: str = ""
    research_only: bool | None = None
    preopen_authority: bool | None = None
    natural_authority: bool | None = None
    reservation_wait_seconds: Decimal | None = None
    failure_reasons: tuple[str, ...] = ()
    last_stage: str = ""
    unfinished_stages: tuple[str, ...] = ()
    stages: tuple[DecisionCaptureStage, ...] = ()


class _InvalidCapture(ValueError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise _InvalidCapture("decision_capture_" + code)


def _no_constant(_value: str) -> Any:
    raise ValueError("非有限JSON常數")


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise ValueError("重複JSON鍵")
        result[key] = value
    return result


def _object(raw: bytes) -> dict[str, Any]:
    try:
        _validate_json_depth(raw)
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_float=Decimal, parse_constant=_no_constant)
        _require(type(value) is dict, "json_object_required")
        return value
    except (ValueError, UnicodeError, RecursionError, DecimalException) as exc:
        raise _InvalidCapture("decision_capture_json_invalid") from exc


def _same(left: Any, right: Any) -> bool:
    """比對原JSON型別，避免bool、整數與計時小數互相冒充。"""
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(_same(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return bool(left == right)


def _timestamp(value: Any) -> datetime:
    try:
        _require(type(value) is str, "clock_invalid")
        parsed = datetime.fromisoformat(value)
        _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, "clock_invalid")
        return parsed
    except (ValueError, TypeError, OverflowError) as exc:
        raise _InvalidCapture("decision_capture_clock_invalid") from exc


def _optional_bool(value: Any) -> bool | None:
    _require(value is None or type(value) is bool, "saved_state_invalid")
    return value


class _Read:
    def __init__(self, cancel: Callable[[], bool] | None) -> None:
        self.cancel = cancel
        self.files: dict[Path, tuple[bytes, tuple[int, ...]]] = {}

    def cancelled(self) -> None:
        check_read_cancelled()
        if self.cancel is not None and self.cancel():
            raise ReadOperationCancelled("決策擷取狀態讀取取消")

    def read(self, path: Path, maximum: int) -> bytes:
        self.cancelled()
        try:
            _canonical_path(path, "decision_capture", allow_missing=False)
            raw, signature = _read_exact_file(path, maximum=maximum)
        except (OSError, ValueError) as exc:
            raise _InvalidCapture("decision_capture_file_unavailable") from exc
        self.files[path] = (raw, signature)
        self.cancelled()
        return raw

    def finish(self) -> None:
        for path, expected in tuple(self.files.items()):
            self.cancelled()
            try:
                _canonical_path(path, "decision_capture", allow_missing=False)
                raw, signature = _read_exact_file(path, maximum=_MAX_JSON)
            except (OSError, ValueError) as exc:
                raise _InvalidCapture("decision_capture_changed_during_read") from exc
            _require((raw, signature) == expected, "changed_during_read")
        self.cancelled()


def _child_artifacts(reader: _Read, payload: dict[str, Any], run_dir: Path) -> tuple[dict[str, Any], str]:
    children = payload.get("subprocesses")
    if type(children) is not dict:
        raise _InvalidCapture("decision_capture_children_invalid")
    _require(set(children) <= {"snapshot", "evidence"}, "children_invalid")
    snapshot_stderr = ""
    for name, child in children.items():
        _require(type(child) is dict, "children_invalid")
        if child.get("artifact_status") != "complete":
            _require(payload["status"] != "passed" and child.get("artifact_status") == "not_started"
                     and child.get("launch_status") == "failed" and child.get("execution_status") == "failed"
                     and child.get("launch_error_type") in {
                         "FileNotFoundError", "PermissionError", "NotADirectoryError", "ValueError", "TypeError",
                     },
                     "artifacts_incomplete")
            continue
        for stream in ("stdout", "stderr"):
            path = run_dir / f"{name}.{stream}.txt"
            _require(child.get(stream + "_path") == str(path), "artifact_path_mismatch")
            raw = reader.read(path, _MAX_OUTPUT)
            count = child.get(stream + "_artifact_byte_count")
            digest = child.get(stream + "_artifact_sha256")
            _require(type(count) is int and count == len(raw), "artifact_size_mismatch")
            _require(type(digest) is str and _HASH.fullmatch(digest) is not None
                     and digest == sha256(raw).hexdigest(), "artifact_hash_mismatch")
            if name == "snapshot" and stream == "stderr":
                snapshot_stderr = raw.decode("utf-8", errors="replace")
    return children, snapshot_stderr


def _verified(reader: _Read, path: Path, payload: dict[str, Any], now: datetime) -> DecisionCaptureRunStatus:
    _require(payload.get("schema_version") == "decision-evidence-capture.v1"
             and payload.get("task") == "baldr-decision-evidence-capture-daily", "identity_mismatch")
    _require(payload["status"] in _TERMINAL_STATUSES, "terminal_status_invalid")
    run_id = payload.get("run_id")
    if type(run_id) is not str or _RUN_ID.fullmatch(run_id) is None:
        raise _InvalidCapture("decision_capture_run_id_invalid")
    run_dir = path.parent / "runs" / run_id
    receipt_path = run_dir / "receipt.json"
    _require(payload.get("status_path") == str(path) and payload.get("run_dir") == str(run_dir)
             and payload.get("receipt_path") == str(receipt_path), "path_mismatch")
    _require(payload.get("receipt_schema_version") == "decision-evidence-capture-receipt.v1"
             and payload.get("receipt_status") == "complete", "receipt_incomplete")
    digest = payload.get("receipt_sha256")
    raw = reader.read(receipt_path, _MAX_JSON)
    if type(digest) is not str or _HASH.fullmatch(digest) is None or sha256(raw).hexdigest() != digest:
        raise _InvalidCapture("decision_capture_receipt_hash_mismatch")
    receipt = _object(raw)
    _require(_same({key: value for key, value in payload.items() if key != "receipt_sha256"}, receipt),
             "receipt_payload_mismatch")
    started = _timestamp(payload.get("run_started_at"))
    completed = _timestamp(payload.get("run_completed_at"))
    _require(started <= completed <= now and _timestamp(payload.get("completed_at")) == completed,
             "clock_out_of_order_or_future")
    raw_date = payload.get("decision_date")
    decision_date = ""
    if raw_date is not None:
        try:
            parsed = date.fromisoformat(raw_date)
        except (TypeError, ValueError) as exc:
            raise _InvalidCapture("decision_capture_date_invalid") from exc
        _require(parsed.isoformat() == raw_date and parsed <= now.astimezone(_TAIPEI).date(), "date_invalid")
        decision_date = raw_date
    _require(bool(decision_date) or payload["status"] != "passed", "date_invalid")
    children, stderr = _child_artifacts(reader, payload, run_dir)
    snapshot = payload.get("snapshot")
    if type(snapshot) is not dict:
        raise _InvalidCapture("decision_capture_snapshot_invalid")
    saved = _optional_bool(payload.get("snapshot_saved"))
    duplicate = _optional_bool(payload.get("snapshot_duplicate"))
    if "snapshot_saved" in payload:
        _require(_same(saved, snapshot.get("saved")), "saved_state_mismatch")
    if "snapshot_duplicate" in payload:
        _require(_same(duplicate, snapshot.get("duplicate")), "saved_state_mismatch")
    snapshot_execution = children.get("snapshot", {}).get("execution_status", "not_started")
    _require(type(snapshot_execution) is str and _CODE.fullmatch(snapshot_execution) is not None,
             "execution_status_invalid")
    failures = payload.get("failure_reasons")
    if type(failures) is not list or not all(type(value) is str for value in failures):
        raise _InvalidCapture("decision_capture_failure_reasons_invalid")
    if payload["status"] == "passed":
        _require(set(children) == {"snapshot", "evidence"} and not failures
                 and (saved is True or duplicate is True) and snapshot.get("status") == "passed"
                 and type(payload.get("evidence")) is dict and payload["evidence"].get("status") == "passed",
                 "passed_summary_inconsistent")
        for child in children.values():
            _require(type(child.get("returncode")) is int and child["returncode"] == 0
                     and child.get("execution_status") == "returned" and child.get("timed_out") is False
                     and child.get("artifact_status") == "complete", "passed_child_inconsistent")
    summary = summarize_snapshot_diagnostics(stderr)
    if "stage_diagnostics" in snapshot:
        _require(_same(summary, snapshot["stage_diagnostics"]), "stage_diagnostics_mismatch")
    stages = tuple(DecisionCaptureStage(**event) for event in summary["events"])
    safe_reasons = tuple(
        value if _CODE.fullmatch(value) and value.startswith(
            ("snapshot_", "evidence_", "temporal_", "calendar_", "trading_calendar_", "heavy_chain_", "receipt_")
        ) else "unlisted_failure_reason" for value in failures[:64]
    )
    snapshot_status = snapshot.get("status", "unknown")
    _require(type(snapshot_status) is str and _CODE.fullmatch(snapshot_status) is not None, "snapshot_status_invalid")
    temporal_keys = ("capture_mode", "temporal_status", "research_only",
                     "preopen_authority", "natural_authority")
    temporal: dict[str, Any] = {}
    if any(key in payload for key in temporal_keys):
        _require(all(key in payload for key in temporal_keys), "temporal_fields_incomplete")
        mode, status = payload["capture_mode"], payload["temporal_status"]
        _require(type(mode) is str and _CODE.fullmatch(mode) is not None
                 and not any(token in mode.lower() for token in ("preopen", "pre-open", "natural"))
                 and type(status) is str and _CODE.fullmatch(status) is not None,
                 "temporal_fields_invalid")
        _require(all(type(payload[key]) is bool for key in temporal_keys[2:]),
                 "temporal_fields_invalid")
        _require(payload["research_only"] is True
                 and payload["preopen_authority"] is False
                 and payload["natural_authority"] is False,
                 "temporal_authority_unproven")
        for child in (snapshot, payload.get("evidence")):
            if type(child) is dict and any(key in child for key in temporal_keys):
                _require(all(key in child and _same(child[key], payload[key]) for key in temporal_keys),
                         "temporal_child_mismatch")
        temporal = {key: payload[key] for key in temporal_keys}
    wait_seconds: Decimal | None = None
    reservation_wait = payload.get("reservation_wait")
    if reservation_wait is not None:
        _require(type(reservation_wait) is dict, "reservation_wait_invalid")
        raw_wait = reservation_wait.get("elapsed_seconds")
        if raw_wait is not None:
            _require(type(raw_wait) in (int, Decimal) and Decimal(raw_wait).is_finite()
                     and Decimal(0) <= Decimal(raw_wait) <= Decimal(86400),
                     "reservation_wait_invalid")
            wait_seconds = Decimal(raw_wait)
    reader.finish()
    return DecisionCaptureRunStatus(
        path, "verified", raw_status=payload["status"], run_id=run_id,
        decision_date=decision_date, completed_at=payload["completed_at"],
        receipt_path=str(receipt_path), receipt_sha256=digest, snapshot_status=snapshot_status,
        snapshot_saved=saved, snapshot_duplicate=duplicate, snapshot_execution_status=snapshot_execution,
        capture_mode=temporal.get("capture_mode", ""),
        temporal_status=temporal.get("temporal_status", ""),
        research_only=temporal.get("research_only"),
        preopen_authority=temporal.get("preopen_authority"),
        natural_authority=temporal.get("natural_authority"),
        reservation_wait_seconds=wait_seconds,
        failure_reasons=safe_reasons, last_stage=summary["last_stage"] or "",
        unfinished_stages=tuple(summary["unfinished_stages"]), stages=stages,
    )


def read_decision_capture_status(
    status_path: Path, *, observed_at: datetime, check_cancel: Callable[[], bool] | None = None,
) -> DecisionCaptureRunStatus:
    """latest只定位同run原件；核對失敗不宣稱成功，也不掃其他run補值。"""
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at必須有時區")
    reader = _Read(check_cancel)
    reader.cancelled()
    raw_status = "unknown"
    try:
        _require(isinstance(status_path, Path) and status_path.is_absolute()
                 and status_path.name == "latest_status.json" and status_path.parent.name == "decision_evidence_capture",
                 "status_path_invalid")
        if not status_path.exists():
            return DecisionCaptureRunStatus(status_path, "missing", "decision_capture_status_missing")
        payload = _object(reader.read(status_path, _MAX_JSON))
        candidate_status = payload.get("status")
        if type(candidate_status) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", candidate_status):
            raw_status = candidate_status
        _require(raw_status != "unknown", "status_invalid")
        if payload.get("finalized") is not True:
            reader.finish()
            return DecisionCaptureRunStatus(status_path, "not_finalized", "decision_capture_not_finalized", raw_status)
        return _verified(reader, status_path, payload, observed_at)
    except _InvalidCapture as exc:
        return DecisionCaptureRunStatus(status_path, "unverified", str(exc), raw_status)
    except (OSError, ValueError, TypeError, RecursionError, DecimalException):
        return DecisionCaptureRunStatus(status_path, "unverified", "decision_capture_chain_invalid", raw_status)
