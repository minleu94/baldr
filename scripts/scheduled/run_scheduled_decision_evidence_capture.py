"""每日建立 Decision Desk 快照並保存 Evidence Event。

本 orchestrator 只依序呼叫既有的兩個 capture CLI。兩個 CLI 都具備內容
hash 與唯一鍵保護，因此中途失敗後可安全重跑；本檔不修改 Rule、Advice、
Portfolio 狀態，也不觸發任何券商執行。
"""

from __future__ import annotations

import argparse
from contextvars import ContextVar
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_module.decision_snapshot_diagnostics import summarize_snapshot_diagnostics
from data_module.official_trading_calendar import OfficialTradingCalendar
from data_module.config import TWStockConfig
from app_module.evidence_event_importer_dtos import (
    EvidenceCaptureRequest,
    capture_context_identity,
    capture_context_is_valid,
)
from app_module.scheduled_writer_reservation import (
    ScheduledWriterReservationError,
    wait_for_scheduled_writer_reservation,
)
from data_module.ml_storage_capacity import (
    MLStorageChainReservation,
    build_heavy_chain_reservation_handoff_environment,
    release_heavy_chain_reservation,
)

_CHILD_RESERVATION: ContextVar[MLStorageChainReservation | None] = ContextVar(
    "decision_capture_child_reservation", default=None
)


TASK_NAME = "baldr-decision-evidence-capture-daily"
TAIPEI = ZoneInfo("Asia/Taipei")
DECISION_TIME = time(hour=8, minute=30)
EOD_RESEARCH_START = time(hour=13, minute=30)
SCHEMA_VERSION = "decision-evidence-capture.v1"
RECEIPT_SCHEMA_VERSION = "decision-evidence-capture-receipt.v1"
MAX_CHILD_OUTPUT_BYTES = 64 * 1024
TEMPORAL_RECEIPT_FIELDS = (
    "decision_at",
    "as_of",
    "captured_at",
    "capture_mode",
    "temporal_status",
    "research_only",
    "preopen_authority",
    "natural_authority",
    "source_availability_preserved",
    "source_availability_policy",
    "capture_context_hash",
    "capture_context_identity_hash",
)
DEFAULT_SUBPROCESS_TIMEOUT_SECONDS = 120
SCHEDULED_WRITER_RESERVATION_TIMEOUT_SECONDS = 10_500
DECISION_CAPTURE_FINALIZATION_RESERVE_SECONDS = 300
REQUIRED_SNAPSHOT_SECTIONS = frozenset(
    {
        "market_regime",
        "market_breadth",
        "sector_rotation",
        "relative_strength_liquidity",
        "watchlist_trigger",
        "portfolio_alert",
        "risk_prompt",
    }
)


def _configured_path(field_name: str) -> Path:
    """Read a TWStockConfig path default without constructing its I/O config."""

    fields = getattr(TWStockConfig, "__dataclass_fields__")
    field = fields[field_name]
    default_factory = getattr(field, "default_factory", None)
    if callable(default_factory):
        return Path(default_factory()).expanduser().resolve()
    return Path(getattr(field, "default")).expanduser().resolve()


def _canonical_reservation_root(
    *,
    data_root: Path,
    output_root: Path,
    db_path: Path | None,
) -> Path:
    """Keep canonical DB writes on the configured OUTPUT_ROOT lock namespace."""

    resolved_data_root = Path(data_root).expanduser().resolve()
    resolved_output_root = Path(output_root).expanduser().resolve()
    resolved_db = (
        Path(db_path).expanduser().resolve()
        if db_path is not None
        else resolved_data_root / "sqlite" / "twstock.db"
    )
    configured_data_root = _configured_path("data_root")
    configured_output_root = _configured_path("output_root")
    configured_db = configured_data_root / "sqlite" / "twstock.db"
    passed_data_db = resolved_data_root / "sqlite" / "twstock.db"
    if resolved_db == configured_db:
        return configured_output_root
    if resolved_db == passed_data_db and resolved_data_root == configured_data_root:
        return configured_output_root
    return resolved_output_root


@dataclass(frozen=True)
class CliRunResult:
    returncode: int | None
    payload: Mapping[str, Any] | None
    stderr: str
    timed_out: bool = False
    timeout_seconds: float | None = None
    stdout: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    stdout_byte_count: int | None = None
    stderr_byte_count: int | None = None
    stdout_sha256: str | None = None
    stderr_sha256: str | None = None
    stdout_artifact: bytes | None = None
    stderr_artifact: bytes | None = None
    execution_status: str = "returned"
    execution_error_type: str | None = None
    execution_error: str | None = None


@dataclass
class RunContext:
    run_id: str
    run_dir: Path
    receipt_path: Path
    status_path: Path
    started_at: str
    subprocesses: dict[str, dict[str, Any]]
    steps: dict[str, dict[str, Any]]


def _output_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if value is None:
        return b""
    return str(value).encode("utf-8", errors="replace")


def _bounded_output(value: object) -> tuple[bytes, str, bool, int, str]:
    """Return bounded raw bytes, display text, and original size/hash metadata."""

    raw = _output_bytes(value)
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) <= MAX_CHILD_OUTPUT_BYTES:
        captured = raw
        truncated = False
    else:
        marker = b"\n...[output truncated]...\n"
        available = max(0, MAX_CHILD_OUTPUT_BYTES - len(marker))
        head_size = available // 2
        tail_size = available - head_size
        captured = raw[:head_size] + marker + raw[-tail_size:]
        truncated = True
    return (
        captured,
        captured.decode("utf-8", errors="replace"),
        truncated,
        len(raw),
        digest,
    )


def _new_run_id() -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{now}-{uuid.uuid4().hex[:12]}"


def _create_run_context(output_root: Path) -> RunContext:
    capture_root = output_root / "scheduled" / "decision_evidence_capture"
    runs_root = capture_root / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    for _ in range(5):
        run_id = _new_run_id()
        run_dir = runs_root / run_id
        try:
            run_dir.mkdir()
        except FileExistsError:
            continue
        status_path = capture_root / "latest_status.json"
        return RunContext(
            run_id=run_id,
            run_dir=run_dir,
            receipt_path=run_dir / "receipt.json",
            status_path=status_path,
            started_at=datetime.now(timezone.utc).isoformat(),
            subprocesses={},
            steps={},
        )
    raise RuntimeError("unable to allocate a unique decision-evidence capture run")


def _publish_create_only_bytes(path: Path, content: bytes) -> None:
    """Durably publish bytes without replacing an existing destination."""

    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "nt":
            # Windows os.rename is the no-replace MoveFile operation and
            # therefore fails if another writer already published this path.
            os.rename(temporary, path)
        else:
            # A hard-link publish is atomic and cannot replace an existing dst.
            os.link(temporary, path)
            temporary.unlink()
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _write_immutable_json(path: Path, payload: Mapping[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _publish_create_only_bytes(path, text.encode("utf-8"))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _persist_cli_result(context: RunContext, name: str, result: CliRunResult) -> dict[str, Any]:
    if result.stdout_artifact is None:
        stdout_artifact, stdout_text, stdout_truncated, stdout_bytes, stdout_sha256 = _bounded_output(
            result.stdout
        )
    else:
        stdout_artifact = result.stdout_artifact
        stdout_text = result.stdout
        stdout_truncated = result.stdout_truncated
        stdout_bytes = result.stdout_byte_count if result.stdout_byte_count is not None else len(stdout_artifact)
        stdout_sha256 = result.stdout_sha256 or hashlib.sha256(stdout_artifact).hexdigest()
    if result.stderr_artifact is None:
        stderr_artifact, stderr_text, stderr_truncated, stderr_bytes, stderr_sha256 = _bounded_output(
            result.stderr
        )
    else:
        stderr_artifact = result.stderr_artifact
        stderr_text = result.stderr
        stderr_truncated = result.stderr_truncated
        stderr_bytes = result.stderr_byte_count if result.stderr_byte_count is not None else len(stderr_artifact)
        stderr_sha256 = result.stderr_sha256 or hashlib.sha256(stderr_artifact).hexdigest()
    stdout_path = context.run_dir / f"{name}.stdout.txt"
    stderr_path = context.run_dir / f"{name}.stderr.txt"
    metadata: dict[str, Any] = {
        "returncode": result.returncode,
        "timed_out": result.timed_out,
        "timeout_seconds": result.timeout_seconds,
        "stdout_path": str(stdout_path.resolve()),
        "stderr_path": str(stderr_path.resolve()),
        "stdout_byte_count": result.stdout_byte_count if result.stdout_byte_count is not None else stdout_bytes,
        "stderr_byte_count": result.stderr_byte_count if result.stderr_byte_count is not None else stderr_bytes,
        "stdout_sha256": result.stdout_sha256 or stdout_sha256,
        "stderr_sha256": result.stderr_sha256 or stderr_sha256,
        "stdout_truncated": result.stdout_truncated or stdout_truncated,
        "stderr_truncated": result.stderr_truncated or stderr_truncated,
        "stdout_artifact_byte_count": len(stdout_artifact),
        "stderr_artifact_byte_count": len(stderr_artifact),
        "stdout_artifact_sha256": hashlib.sha256(stdout_artifact).hexdigest(),
        "stderr_artifact_sha256": hashlib.sha256(stderr_artifact).hexdigest(),
        "launch_status": (
            "unknown"
            if result.execution_status == "unknown"
            else "returned"
        ),
        "execution_status": result.execution_status,
        "execution_error_type": result.execution_error_type,
        "execution_error": result.execution_error,
        "artifact_status": "pending",
    }
    context.subprocesses[name] = metadata
    _publish_create_only_bytes(stdout_path, stdout_artifact)
    _publish_create_only_bytes(stderr_path, stderr_artifact)
    metadata["artifact_status"] = "complete"
    return metadata


def _mark_child_started(
    context: RunContext,
    name: str,
    *,
    timeout_seconds: float,
) -> None:
    context.subprocesses[name] = {
        "returncode": None,
        "timed_out": False,
        "timeout_seconds": timeout_seconds,
        "launch_status": "started",
        "execution_status": "started",
        "artifact_status": "not_started",
    }


def next_unreached_taipei_decision_at(now: datetime | None = None) -> datetime:
    """回傳尚未到達的下一個台北 08:30 日曆決策時間。

    回傳值仍須交由 :class:`OfficialTradingCalendar` 驗證；休市或未知日期
    不得建立 Decision Desk 或 Evidence 紀錄。
    """

    current = now or datetime.now(TAIPEI)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now 必須包含時區")
    current_taipei = current.astimezone(TAIPEI)
    candidate = datetime.combine(
        current_taipei.date(),
        DECISION_TIME,
        tzinfo=TAIPEI,
    )
    if current_taipei >= candidate:
        candidate += timedelta(days=1)
    return candidate


def latest_reached_taipei_decision_at(now: datetime | None = None) -> datetime:
    """回傳最近一個已到達的台北 08:30 日曆決策時間。

    Windows 排程在台灣 08:30 前執行時，若選下一個尚未到達的 cutoff，
    capture CLI 會收到 future decision date。排程入口因此只選已到達的
    日曆 cutoff；這個值只作為 ``calendar_decision_at`` 的日期選擇器，
    不會冒充實際的 ``decision_at``。實際決策與 capture 時間由 caller
    明確傳入或使用本次 aware capture clock，再由下游驗證。
    """

    current = now or datetime.now(TAIPEI)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now 必須包含時區")
    current_taipei = current.astimezone(TAIPEI)
    candidate = datetime.combine(
        current_taipei.date(),
        DECISION_TIME,
        tzinfo=TAIPEI,
    )
    if candidate > current_taipei:
        candidate -= timedelta(days=1)
    return candidate


def _resolve_calendar_decision_at(
    *,
    checked_at: datetime,
    resolved_decision_at: datetime,
    explicit_decision_at: datetime | None,
    as_of: date | str | None,
    calendar_decision_at: datetime | None,
) -> tuple[datetime, date | None, str]:
    explicit_as_of = _as_of_date(as_of)
    explicit_calendar_decision_at = (
        _taipei_datetime(calendar_decision_at, field_name="calendar_decision_at")
        if calendar_decision_at is not None
        else None
    )
    if explicit_calendar_decision_at is not None:
        if (
            explicit_calendar_decision_at.timetz().replace(tzinfo=None)
            != DECISION_TIME
        ):
            raise ValueError("calendar_decision_at must be Asia/Taipei 08:30")
        resolved_calendar_decision_at = explicit_calendar_decision_at
        decision_date_basis = "explicit_calendar_decision_at"
    elif explicit_as_of is not None:
        resolved_calendar_decision_at = datetime.combine(
            explicit_as_of,
            DECISION_TIME,
            tzinfo=TAIPEI,
        )
        decision_date_basis = "explicit_as_of_date"
    elif explicit_decision_at is not None:
        # An explicit actual decision timestamp also supplies the natural-day
        # selector when no separate as-of/calendar selector is given.
        resolved_calendar_decision_at = datetime.combine(
            resolved_decision_at.date(),
            DECISION_TIME,
            tzinfo=TAIPEI,
        )
        decision_date_basis = "explicit_decision_at_calendar_date"
    else:
        resolved_calendar_decision_at = latest_reached_taipei_decision_at(checked_at)
        decision_date_basis = "latest_reached_calendar_decision_at"

    if explicit_as_of is not None and explicit_as_of != resolved_calendar_decision_at.date():
        raise ValueError("as_of must match calendar_decision_at date")
    return resolved_calendar_decision_at, explicit_as_of, decision_date_basis


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _run_json_cli(
    command: Sequence[str],
    *,
    timeout_seconds: float = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
) -> CliRunResult:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds 必須大於 0")
    environment = os.environ.copy()
    environment.setdefault("PYTHONUTF8", "1")
    try:
        reservation = _CHILD_RESERVATION.get()
        if reservation is not None and len(command) > 1 and Path(command[1]).name == "capture_evidence_events.py":
            environment = build_heavy_chain_reservation_handoff_environment(
                reservation, environment=environment, parent_pid=os.getpid()
            )
            with subprocess.Popen(
                list(command), cwd=REPO_ROOT, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=environment,
            ) as child:
                try:
                    reservation.authorize_child(child.pid)
                    stdout, stderr = child.communicate(timeout=timeout_seconds)
                except BaseException:
                    child.kill()
                    child.communicate()
                    raise
                completed = subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
        else:
            completed = subprocess.run(
                list(command),
                cwd=REPO_ROOT,
                capture_output=True,
                text=False,
                check=False,
                env=environment,
                timeout=timeout_seconds,
            )
    except subprocess.TimeoutExpired as exc:
        stdout_artifact, stdout_text, stdout_truncated, stdout_bytes, stdout_sha256 = _bounded_output(
            exc.stdout
        )
        stderr_artifact, stderr_text, stderr_truncated, stderr_bytes, stderr_sha256 = _bounded_output(
            exc.stderr
        )
        return CliRunResult(
            returncode=None,
            payload=None,
            stderr=stderr_text,
            timed_out=True,
            timeout_seconds=timeout_seconds,
            stdout=stdout_text,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            stdout_byte_count=stdout_bytes,
            stderr_byte_count=stderr_bytes,
            stdout_sha256=stdout_sha256,
            stderr_sha256=stderr_sha256,
            stdout_artifact=stdout_artifact,
            stderr_artifact=stderr_artifact,
            execution_status="timed_out",
        )
    except (FileNotFoundError, PermissionError, NotADirectoryError):
        # 這些例外發生於 Popen 建立 child 前，交由外層保留明確 launch failure。
        raise
    except Exception as exc:  # noqa: BLE001 - child 已啟動時只能保守標 unknown
        stdout_artifact, stdout_text, stdout_truncated, stdout_bytes, stdout_sha256 = _bounded_output(
            getattr(exc, "stdout", b"")
        )
        stderr_artifact, stderr_text, stderr_truncated, stderr_bytes, stderr_sha256 = _bounded_output(
            getattr(exc, "stderr", b"")
        )
        return CliRunResult(
            returncode=None,
            payload=None,
            stderr=stderr_text,
            timed_out=False,
            timeout_seconds=timeout_seconds,
            stdout=stdout_text,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            stdout_byte_count=stdout_bytes,
            stderr_byte_count=stderr_bytes,
            stdout_sha256=stdout_sha256,
            stderr_sha256=stderr_sha256,
            stdout_artifact=stdout_artifact,
            stderr_artifact=stderr_artifact,
            execution_status="unknown",
            execution_error_type=type(exc).__name__,
            execution_error=str(exc),
        )
    stdout_artifact, stdout_text, stdout_truncated, stdout_bytes, stdout_sha256 = _bounded_output(
        completed.stdout
    )
    stderr_artifact, stderr_text, stderr_truncated, stderr_bytes, stderr_sha256 = _bounded_output(
        completed.stderr
    )
    payload: Mapping[str, Any] | None = None
    try:
        decoded = json.loads(_output_bytes(completed.stdout))
        if isinstance(decoded, dict):
            payload = decoded
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        payload = None
    return CliRunResult(
        returncode=completed.returncode,
        payload=payload,
        stderr=stderr_text,
        stdout=stdout_text,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        stdout_byte_count=stdout_bytes,
        stderr_byte_count=stderr_bytes,
        stdout_sha256=stdout_sha256,
        stderr_sha256=stderr_sha256,
        stdout_artifact=stdout_artifact,
        stderr_artifact=stderr_artifact,
    )


def _non_negative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"{label} 必須是非負整數")
    return value


def _temporal_receipt_failures(
    payload: Mapping[str, Any],
    expected: Mapping[str, Any] | None,
) -> list[str]:
    if expected is None:
        return []
    return [
        f"temporal_receipt_mismatch:{field}"
        for field in TEMPORAL_RECEIPT_FIELDS
        if payload.get(field) != expected.get(field)
    ]


def _temporal_receipt_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {field: payload.get(field) for field in TEMPORAL_RECEIPT_FIELDS}


def _persisted_capture_context(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    value = payload.get("persisted_capture_context")
    return dict(value) if isinstance(value, Mapping) else None


def _persisted_context_failures(
    payload: Mapping[str, Any],
    expected: Mapping[str, Any] | None,
    *,
    prefix: str,
) -> list[str]:
    if expected is None:
        return []
    persisted = _persisted_capture_context(payload)
    if persisted is None:
        return [f"{prefix}_persisted_capture_context_missing"]
    if not capture_context_is_valid(persisted):
        return [f"{prefix}_persisted_capture_context_invalid"]
    if capture_context_identity(persisted) != capture_context_identity(expected):
        return [f"{prefix}_persisted_capture_context_identity_mismatch"]
    return []


def _snapshot_step(
    result: CliRunResult,
    *,
    expected_temporal: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    payload = result.payload
    failures: list[str] = []
    if result.timed_out:
        failures.append("snapshot_cli_timeout")
    elif result.returncode != 0:
        failures.append(f"snapshot_cli_exit:{result.returncode}")
    if result.execution_status == "unknown":
        failures.append(
            "snapshot_cli_execution_unknown"
            + (
                f":{result.execution_error_type}"
                if result.execution_error_type
                else ""
            )
        )
    if payload is None:
        failures.append("snapshot_json_invalid")
        return (
            {
                "status": (
                    "timeout"
                    if result.timed_out
                    else ("unknown" if result.execution_status == "unknown" else "failed")
                ),
                "saved": None,
                "duplicate": None,
                "stderr": result.stderr,
                "timeout_seconds": result.timeout_seconds,
                "execution_status": result.execution_status,
                "execution_error_type": result.execution_error_type,
                "execution_error": result.execution_error,
                "stage_diagnostics": summarize_snapshot_diagnostics(result.stderr),
            },
            failures,
        )

    saved = payload.get("saved") is True
    duplicate = payload.get("skipped_duplicate") is True
    if payload.get("dry_run") is not False:
        failures.append("snapshot_confirm_not_effective")
    if not saved and not duplicate:
        failures.append("snapshot_not_saved_or_duplicate")
    raw_sections_seen = payload.get("sections_seen")
    raw_sections_missing = payload.get("sections_missing")
    if not isinstance(raw_sections_seen, list) or not all(
        isinstance(section, str) for section in raw_sections_seen
    ):
        failures.append("snapshot_sections_seen_invalid")
        sections_seen: list[str] = []
    else:
        sections_seen = list(raw_sections_seen)
    if not isinstance(raw_sections_missing, list) or not all(
        isinstance(section, str) for section in raw_sections_missing
    ):
        failures.append("snapshot_sections_missing_invalid")
        sections_missing: list[str] = []
    else:
        sections_missing = list(raw_sections_missing)
    missing_required = sorted(REQUIRED_SNAPSHOT_SECTIONS - set(sections_seen))
    if missing_required:
        failures.append(
            "snapshot_required_sections_missing:" + ",".join(missing_required)
        )
    if sections_missing:
        failures.append(
            "snapshot_sections_reported_missing:" + ",".join(
                sorted(set(sections_missing))
            )
        )
    failures.extend(_temporal_receipt_failures(payload, expected_temporal))
    failures.extend(
        _persisted_context_failures(
            payload,
            expected_temporal,
            prefix="snapshot",
        )
    )
    step = {
        "status": "passed" if not failures else "failed",
        "stage_diagnostics": summarize_snapshot_diagnostics(result.stderr),
        "saved": saved,
        "duplicate": duplicate,
        "snapshot_id": payload.get("snapshot_id"),
        "snapshot_hash": payload.get("snapshot_hash"),
        "quality": payload.get("quality"),
        "sections_seen": sections_seen,
        "sections_missing": sections_missing,
        "required_sections": sorted(REQUIRED_SNAPSHOT_SECTIONS),
        "warnings_count": payload.get("warnings_count"),
        "execution_status": result.execution_status,
        "execution_error_type": result.execution_error_type,
        **_temporal_receipt_payload(payload),
        "persisted_capture_context": _persisted_capture_context(payload),
    }
    if result.stderr and failures:
        step["stderr"] = result.stderr
    return step, failures


def _evidence_step(
    result: CliRunResult,
    *,
    expected_temporal: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    payload = result.payload
    failures: list[str] = []
    if result.timed_out:
        failures.append("evidence_cli_timeout")
    elif result.returncode != 0:
        failures.append(f"evidence_cli_exit:{result.returncode}")
    if result.execution_status == "unknown":
        failures.append(
            "evidence_cli_execution_unknown"
            + (
                f":{result.execution_error_type}"
                if result.execution_error_type
                else ""
            )
        )
    if payload is None:
        failures.append("evidence_json_invalid")
        return (
            {
                "status": (
                    "timeout"
                    if result.timed_out
                    else ("unknown" if result.execution_status == "unknown" else "failed")
                ),
                "events_seen": None,
                "events_inserted": None,
                "duplicates": None,
                "failures": None,
                "stderr": result.stderr,
                "timeout_seconds": result.timeout_seconds,
                "execution_status": result.execution_status,
                "execution_error_type": result.execution_error_type,
                "execution_error": result.execution_error,
            },
            failures,
        )

    try:
        seen = _non_negative_int(
            payload.get("events_seen"),
            label="events_seen",
        )
        inserted = _non_negative_int(
            payload.get("events_inserted"),
            label="events_inserted",
        )
        duplicates = _non_negative_int(
            payload.get("events_skipped_duplicate"),
            label="events_skipped_duplicate",
        )
        event_failures = _non_negative_int(
            payload.get("events_failed"),
            label="events_failed",
        )
    except TypeError as exc:
        failures.append(f"evidence_counts_invalid:{exc}")
        seen = 0
        inserted = 0
        duplicates = 0
        event_failures = 1

    if payload.get("dry_run") is not False:
        failures.append("evidence_confirm_not_effective")
    if seen == 0:
        failures.append("evidence_events_empty")
    if inserted == 0 and duplicates == 0:
        failures.append("evidence_no_insert_or_duplicate")
    if event_failures:
        failures.append(f"evidence_events_failed:{event_failures}")
    diagnostics = payload.get("diagnostics")
    error_diagnostics = []
    if isinstance(diagnostics, list):
        error_diagnostics = [
            item
            for item in diagnostics
            if isinstance(item, dict) and item.get("severity") == "error"
        ]
    if error_diagnostics:
        failures.append(f"evidence_error_diagnostics:{len(error_diagnostics)}")
    failures.extend(_temporal_receipt_failures(payload, expected_temporal))
    failures.extend(
        _persisted_context_failures(
            payload,
            expected_temporal,
            prefix="evidence",
        )
    )

    step = {
        "status": "passed" if not failures else "failed",
        "events_seen": seen,
        "events_inserted": inserted,
        "duplicates": duplicates,
        "failures": event_failures + len(error_diagnostics),
        "warnings_count": payload.get("warnings_count"),
        "diagnostics_by_code": dict(payload.get("diagnostics_by_code") or {}),
        "event_type_counts": dict(payload.get("event_type_counts") or {}),
        "quality_counts": dict(payload.get("quality_counts") or {}),
        "execution_status": result.execution_status,
        "execution_error_type": result.execution_error_type,
        **_temporal_receipt_payload(payload),
        "persisted_capture_context": _persisted_capture_context(payload),
    }
    if result.stderr and failures:
        step["stderr"] = result.stderr
    return step, failures


def _base_payload(
    *,
    calendar_decision_at: datetime,
    decision_at: datetime,
    as_of_date: date,
    captured_at: datetime,
    capture_mode: str,
    temporal: Mapping[str, Any],
    checked_at: datetime,
    status_path: Path,
    run_context: RunContext,
    db_path: Path | None,
    decision_date_basis: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "task": TASK_NAME,
        "status": "running",
        "checked_at": checked_at.isoformat(timespec="seconds"),
        "calendar_decision_at": calendar_decision_at.isoformat(timespec="seconds"),
        "decision_at": decision_at.isoformat(),
        "decision_date": as_of_date.isoformat(),
        "as_of": as_of_date.isoformat(),
        "captured_at": captured_at.isoformat(),
        "decision_timezone": "Asia/Taipei",
        "decision_time": decision_at.timetz().replace(tzinfo=None).isoformat(),
        "calendar_decision_time": DECISION_TIME.isoformat(),
        "capture_mode": capture_mode,
        "temporal_status": temporal["temporal_status"],
        "research_only": temporal["research_only"],
        "preopen_authority": temporal["preopen_authority"],
        "natural_authority": temporal["natural_authority"],
        "source_availability_preserved": temporal["source_availability_preserved"],
        "source_availability_policy": temporal["source_availability_policy"],
        "capture_context_hash": temporal["capture_context_hash"],
        "capture_context_identity_hash": temporal["capture_context_identity_hash"],
        "decision_date_basis": decision_date_basis,
        "trading_calendar_validated": False,
        "trading_calendar_is_open": None,
        "trading_calendar_reason": None,
        "maturity_date_inferred": False,
        "status_path": str(status_path.resolve()),
        "run_id": run_context.run_id,
        "run_started_at": run_context.started_at,
        "receipt_path": str(run_context.receipt_path.resolve()),
        "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "db_path": str(db_path.resolve()) if db_path is not None else None,
        "confirm_capture": True,
        "safety_boundary": {
            "writes_decision_desk_snapshot": True,
            "writes_evidence_events": True,
            "changes_rule_state": False,
            "changes_advice_state": False,
            "changes_portfolio_state": False,
            "broker_execution": False,
        },
    }


def _taipei_datetime(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} 必須包含時區")
    return value.astimezone(TAIPEI)


def _as_of_date(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip()[:10])


def _default_capture_mode(captured_at: datetime, requested: str | None) -> str:
    if requested is not None and str(requested).strip():
        return str(requested).strip()
    local = captured_at.astimezone(TAIPEI)
    return "eod_research" if local.time() >= EOD_RESEARCH_START else "research_only"


def _is_definitely_prelaunch_exception(exc: BaseException) -> bool:
    """判斷例外是否明確發生在 child 建立前。"""

    return isinstance(
        exc,
        (
            FileNotFoundError,
            PermissionError,
            NotADirectoryError,
            ValueError,
            TypeError,
        ),
    )


def _run_once(
    *,
    data_root: Path,
    output_root: Path,
    db_path: Path | None = None,
    now: datetime | None = None,
    decision_at: datetime | None = None,
    as_of: date | str | None = None,
    captured_at: datetime | None = None,
    capture_mode: str | None = None,
    calendar_decision_at: datetime | None = None,
    python_executable: str | None = None,
    subprocess_timeout_seconds: int = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    calendar: OfficialTradingCalendar | None = None,
    reservation_wait: Mapping[str, object] | None = None,
    run_context: RunContext,
) -> dict[str, Any]:
    checked_raw = now or datetime.now(TAIPEI)
    checked_at = _taipei_datetime(checked_raw, field_name="now")
    resolved_captured_at = _taipei_datetime(
        captured_at or checked_at,
        field_name="captured_at",
    )
    resolved_decision_at = _taipei_datetime(
        decision_at or resolved_captured_at,
        field_name="decision_at",
    )
    if resolved_captured_at < resolved_decision_at:
        raise ValueError("captured_at 不得早於 decision_at")

    explicit_as_of = _as_of_date(as_of)
    explicit_calendar_decision_at = (
        _taipei_datetime(calendar_decision_at, field_name="calendar_decision_at")
        if calendar_decision_at is not None
        else None
    )
    if explicit_calendar_decision_at is not None:
        if (
            explicit_calendar_decision_at.timetz().replace(tzinfo=None)
            != DECISION_TIME
        ):
            raise ValueError("calendar_decision_at 必須對應 Asia/Taipei 08:30")
        resolved_calendar_decision_at = explicit_calendar_decision_at
        decision_date_basis = "explicit_calendar_decision_at"
    elif explicit_as_of is not None:
        resolved_calendar_decision_at = datetime.combine(
            explicit_as_of,
            DECISION_TIME,
            tzinfo=TAIPEI,
        )
        decision_date_basis = "explicit_as_of_date"
    elif decision_at is not None:
        # An explicit actual decision timestamp also supplies the natural-day
        # selector when no separate as-of/calendar selector is given.
        resolved_calendar_decision_at = datetime.combine(
            resolved_decision_at.date(),
            DECISION_TIME,
            tzinfo=TAIPEI,
        )
        decision_date_basis = "explicit_decision_at_calendar_date"
    else:
        resolved_calendar_decision_at = latest_reached_taipei_decision_at(checked_at)
        decision_date_basis = "latest_reached_calendar_decision_at"

    if explicit_as_of is not None and explicit_as_of != resolved_calendar_decision_at.date():
        raise ValueError("as_of 必須與 calendar_decision_at 同一台北自然日")
    resolved_as_of_date = explicit_as_of or resolved_calendar_decision_at.date()
    resolved_capture_mode = _default_capture_mode(
        resolved_captured_at,
        capture_mode,
    )
    capture_request = EvidenceCaptureRequest(
        source="scheduled-decision-evidence",
        decision_date=resolved_as_of_date,
        as_of=resolved_as_of_date,
        decision_at=resolved_decision_at,
        captured_at=resolved_captured_at,
        capture_mode=resolved_capture_mode,
    )
    temporal = capture_request.temporal_summary
    status_path = run_context.status_path
    payload = _base_payload(
        calendar_decision_at=resolved_calendar_decision_at,
        decision_at=resolved_decision_at,
        as_of_date=resolved_as_of_date,
        captured_at=resolved_captured_at,
        capture_mode=resolved_capture_mode,
        temporal=temporal,
        checked_at=checked_at,
        status_path=status_path,
        run_context=run_context,
        db_path=db_path,
        decision_date_basis=decision_date_basis,
    )
    if reservation_wait is not None:
        payload["reservation_wait"] = dict(reservation_wait)

    calendar_service = calendar or OfficialTradingCalendar(db_path=db_path)
    try:
        is_trading_day, calendar_reason = (
            calendar_service.is_official_trading_day(
                resolved_calendar_decision_at.date()
            )
        )
    except Exception as exc:  # noqa: BLE001 - 必須持久化 fail-closed 狀態
        is_trading_day = None
        calendar_reason = f"calendar_exception:{type(exc).__name__}"
    payload["trading_calendar_validated"] = is_trading_day is not None
    payload["trading_calendar_is_open"] = is_trading_day
    payload["trading_calendar_reason"] = calendar_reason
    if (
        is_trading_day is True
        and reservation_wait is not None
        and reservation_wait.get("status") != "acquired"
    ):
        payload.update(
            {
                "status": "blocked_reservation_not_acquired",
                "failure_reasons": ["canonical_writer_reservation_not_acquired"],
                "snapshot": {
                    "status": "not_run",
                    "saved": False,
                    "duplicate": False,
                    "reason": "canonical_writer_reservation_not_acquired",
                },
                "evidence": {
                    "status": "not_run",
                    "events_seen": 0,
                    "events_inserted": 0,
                    "duplicates": 0,
                    "failures": 0,
                    "reason": "canonical_writer_reservation_not_acquired",
                },
                "snapshot_saved": False,
                "snapshot_duplicate": False,
                "events_inserted": 0,
                "events_duplicates": 0,
                "events_failures": 0,
                "safety_boundary": {
                    **dict(payload["safety_boundary"]),
                    "writes_decision_desk_snapshot": False,
                    "writes_evidence_events": False,
                },
            }
        )
        _atomic_write_json(status_path, payload)
        return payload
    _atomic_write_json(status_path, payload)
    if is_trading_day is not True:
        safety_boundary = dict(payload["safety_boundary"])
        safety_boundary["writes_decision_desk_snapshot"] = False
        safety_boundary["writes_evidence_events"] = False
        payload.update(
            {
                "status": (
                    "skipped_non_trading_day"
                    if is_trading_day is False
                    else "degraded_calendar_unknown"
                ),
                "failure_reasons": [
                    (
                        f"non_trading_day:{calendar_reason}"
                        if is_trading_day is False
                        else f"trading_calendar_unknown:{calendar_reason}"
                    )
                ],
                "snapshot": {
                    "status": "not_run",
                    "saved": False,
                    "duplicate": False,
                    "reason": "official_market_not_open",
                },
                "evidence": {
                    "status": "not_run",
                    "events_seen": 0,
                    "events_inserted": 0,
                    "duplicates": 0,
                    "failures": 0,
                    "reason": "official_market_not_open",
                },
                "snapshot_saved": False,
                "snapshot_duplicate": False,
                "events_inserted": 0,
                "events_duplicates": 0,
                "events_failures": 0,
                "safety_boundary": safety_boundary,
            }
        )
        return payload

    interpreter = python_executable or sys.executable
    common_args = [
        "--decision-date",
        resolved_as_of_date.isoformat(),
        "--as-of",
        resolved_as_of_date.isoformat(),
        "--decision-at",
        resolved_decision_at.isoformat(),
        "--captured-at",
        resolved_captured_at.isoformat(),
        "--capture-mode",
        resolved_capture_mode,
        "--data-root",
        str(data_root),
        "--output-root",
        str(output_root),
        "--json-output",
    ]
    if db_path is not None:
        common_args.extend(("--db-path", str(db_path)))

    failures: list[str] = []
    snapshot_execution: dict[str, Any] | None = None
    snapshot_execution_state: dict[str, Any] | None = None
    try:
        _mark_child_started(
            run_context,
            "snapshot",
            timeout_seconds=subprocess_timeout_seconds,
        )
        snapshot_result = _run_json_cli(
            [
                interpreter,
                str(
                    REPO_ROOT
                    / "scripts"
                    / "capture_decision_desk_snapshot.py"
                ),
                *common_args,
                "--stage-diagnostics",
                "--confirm",
            ],
            timeout_seconds=subprocess_timeout_seconds,
        )
        snapshot_execution = _persist_cli_result(
            run_context,
            "snapshot",
            snapshot_result,
        )
        expected_temporal = _temporal_receipt_payload(payload)
        snapshot, snapshot_failures = _snapshot_step(
            snapshot_result,
            expected_temporal=expected_temporal,
        )
    except Exception as exc:  # noqa: BLE001
        snapshot_execution_state = run_context.subprocesses.get("snapshot")
        if snapshot_execution_state is not None:
            snapshot = {
                "status": "unknown",
                "saved": None,
                "duplicate": None,
                "reason": (
                    "snapshot_artifact_persistence_failed"
                    if snapshot_execution_state.get("artifact_status") == "pending"
                    else (
                        "snapshot_launch_failed"
                        if (
                            snapshot_execution_state.get("launch_status") == "started"
                            and _is_definitely_prelaunch_exception(exc)
                        )
                        else "snapshot_execution_unknown"
                    )
                ),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "execution": snapshot_execution_state,
            }
        else:
            snapshot = {
                "status": "failed",
                "saved": False,
                "duplicate": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        snapshot_failures = [
            f"snapshot_step_exception:{type(exc).__name__}"
        ]
        if snapshot_execution_state is not None:
            if snapshot_execution_state.get("launch_status") == "started":
                definitely_prelaunch = _is_definitely_prelaunch_exception(exc)
                snapshot_execution_state["launch_status"] = (
                    "failed" if definitely_prelaunch else "unknown"
                )
                snapshot_execution_state["execution_status"] = (
                    "failed" if definitely_prelaunch else "unknown"
                )
                snapshot_execution_state["launch_error_type"] = type(exc).__name__
                if not definitely_prelaunch:
                    snapshot_execution_state["execution_error_type"] = type(exc).__name__
                    snapshot_execution_state["execution_error"] = str(exc)
            safety_boundary = dict(payload["safety_boundary"])
            safety_boundary["writes_decision_desk_snapshot"] = None
            safety_boundary["writes_evidence_events"] = False
            payload["safety_boundary"] = safety_boundary
        if snapshot_execution_state is not None:
            snapshot["execution"] = snapshot_execution_state
    snapshot_execution_state = run_context.subprocesses.get("snapshot")
    if snapshot.get("saved") is None and snapshot_execution_state is not None:
        safety_boundary = dict(payload["safety_boundary"])
        safety_boundary["writes_decision_desk_snapshot"] = None
        payload["safety_boundary"] = safety_boundary
    if snapshot_execution is not None:
        snapshot["execution"] = snapshot_execution
    run_context.steps["snapshot"] = dict(snapshot)
    failures.extend(snapshot_failures)
    payload["snapshot"] = snapshot

    if failures:
        payload["evidence"] = {
            "status": "not_run",
            "events_inserted": 0,
            "duplicates": 0,
            "failures": 0,
            "reason": "snapshot_step_failed",
        }
        run_context.steps["evidence"] = dict(payload["evidence"])
    else:
        evidence_execution: dict[str, Any] | None = None
        evidence_execution_state: dict[str, Any] | None = None
        try:
            _mark_child_started(
                run_context,
                "evidence",
                timeout_seconds=subprocess_timeout_seconds,
            )
            evidence_result = _run_json_cli(
                [
                    interpreter,
                    str(
                        REPO_ROOT
                        / "scripts"
                        / "capture_evidence_events.py"
                    ),
                    "--source",
                    "all",
                    *common_args,
                    "--confirm",
                ],
                timeout_seconds=subprocess_timeout_seconds,
            )
            evidence_execution = _persist_cli_result(
                run_context,
                "evidence",
                evidence_result,
            )
            evidence, evidence_failures = _evidence_step(
                evidence_result,
                expected_temporal=expected_temporal,
            )
        except Exception as exc:  # noqa: BLE001
            evidence_execution_state = run_context.subprocesses.get("evidence")
            if evidence_execution_state is not None:
                evidence = {
                    "status": "unknown",
                    "events_seen": None,
                    "events_inserted": None,
                    "duplicates": None,
                    "failures": None,
                    "reason": (
                        "evidence_artifact_persistence_failed"
                        if evidence_execution_state.get("artifact_status") == "pending"
                        else (
                            "evidence_launch_failed"
                            if (
                                evidence_execution_state.get("launch_status") == "started"
                                and _is_definitely_prelaunch_exception(exc)
                            )
                            else "evidence_execution_unknown"
                        )
                    ),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "execution": evidence_execution_state,
                }
            else:
                evidence = {
                    "status": "failed",
                    "events_inserted": 0,
                    "duplicates": 0,
                    "failures": 1,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            evidence_failures = [
                f"evidence_step_exception:{type(exc).__name__}"
            ]
            if evidence_execution_state is not None:
                if evidence_execution_state.get("launch_status") == "started":
                    definitely_prelaunch = _is_definitely_prelaunch_exception(exc)
                    evidence_execution_state["launch_status"] = (
                        "failed" if definitely_prelaunch else "unknown"
                    )
                    evidence_execution_state["execution_status"] = (
                        "failed" if definitely_prelaunch else "unknown"
                    )
                    evidence_execution_state["launch_error_type"] = type(exc).__name__
                    if not definitely_prelaunch:
                        evidence_execution_state["execution_error_type"] = type(exc).__name__
                        evidence_execution_state["execution_error"] = str(exc)
                safety_boundary = dict(payload["safety_boundary"])
                safety_boundary["writes_evidence_events"] = None
                payload["safety_boundary"] = safety_boundary
            if evidence_execution_state is not None:
                evidence["execution"] = evidence_execution_state
        evidence_execution_state = run_context.subprocesses.get("evidence")
        if evidence.get("events_inserted") is None and evidence_execution_state is not None:
            safety_boundary = dict(payload["safety_boundary"])
            safety_boundary["writes_evidence_events"] = None
            payload["safety_boundary"] = safety_boundary
        if evidence_execution is not None:
            evidence["execution"] = evidence_execution
        run_context.steps["evidence"] = dict(evidence)
        payload["evidence"] = evidence
        failures.extend(evidence_failures)

    evidence_payload = payload["evidence"]
    payload.update(
        {
            "status": (
                "degraded"
                if any("timeout" in reason for reason in failures)
                else ("failed" if failures else "passed")
            ),
            "failure_reasons": failures,
            "snapshot_saved": snapshot["saved"],
            "snapshot_duplicate": snapshot["duplicate"],
            "events_inserted": evidence_payload["events_inserted"],
            "events_duplicates": evidence_payload["duplicates"],
            "events_failures": evidence_payload["failures"],
            "current_capture_context": _temporal_receipt_payload(payload),
            "persisted_snapshot_capture_context": _persisted_capture_context(snapshot),
            "persisted_event_capture_context": _persisted_capture_context(evidence_payload),
            "subprocess_timeout_seconds": subprocess_timeout_seconds,
            "subprocesses": dict(run_context.subprocesses),
        }
    )
    return payload


def _exception_payload(context: RunContext, exc: Exception) -> dict[str, Any]:
    snapshot = dict(
        context.steps.get(
            "snapshot",
            {
                "status": "not_run",
                "saved": False,
                "duplicate": False,
                "reason": "orchestrator_exception",
            },
        )
    )
    evidence = dict(
        context.steps.get(
            "evidence",
            {
                "status": "not_run",
                "events_seen": 0,
                "events_inserted": 0,
                "duplicates": 0,
                "failures": 0,
                "reason": "orchestrator_exception",
            },
        )
    )
    if "snapshot" not in context.steps and "snapshot" in context.subprocesses:
        snapshot = {
            "status": "unknown",
            "saved": None,
            "duplicate": None,
            "reason": "orchestrator_exception_after_snapshot_child",
            "execution": context.subprocesses["snapshot"],
        }
    if "evidence" not in context.steps and "evidence" in context.subprocesses:
        evidence = {
            "status": "unknown",
            "events_seen": None,
            "events_inserted": None,
            "duplicates": None,
            "failures": None,
            "reason": "orchestrator_exception_after_evidence_child",
            "execution": context.subprocesses["evidence"],
        }

    snapshot_write: bool | None
    if "snapshot" in context.steps:
        snapshot_write = snapshot.get("saved") if isinstance(snapshot.get("saved"), bool) else None
    elif "snapshot" in context.subprocesses:
        snapshot_write = None
    else:
        snapshot_write = False
    if "evidence" in context.steps:
        if evidence.get("status") == "not_run":
            evidence_write = False
        elif evidence.get("events_inserted") is None:
            evidence_write = None
        else:
            evidence_write = True
    elif "evidence" in context.subprocesses:
        evidence_write = None
    else:
        evidence_write = False
    payload = {
        "schema_version": SCHEMA_VERSION,
        "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "task": TASK_NAME,
        "status": "failed",
        "run_id": context.run_id,
        "run_started_at": context.started_at,
        "status_path": str(context.status_path.resolve()),
        "receipt_path": str(context.receipt_path.resolve()),
        "failure_reasons": [f"orchestrator_exception:{type(exc).__name__}"],
        "error_type": type(exc).__name__,
        "error": str(exc),
        "snapshot": snapshot,
        "evidence": evidence,
        "snapshot_saved": snapshot.get("saved"),
        "snapshot_duplicate": snapshot.get("duplicate"),
        "events_inserted": evidence.get("events_inserted"),
        "events_duplicates": evidence.get("duplicates"),
        "events_failures": evidence.get("failures"),
        "subprocesses": dict(context.subprocesses),
        "safety_boundary": {
            "writes_decision_desk_snapshot": snapshot_write,
            "writes_evidence_events": evidence_write,
            "changes_rule_state": False,
            "changes_advice_state": False,
            "changes_portfolio_state": False,
            "broker_execution": False,
        },
    }
    reservation_wait = context.steps.get("reservation_wait")
    if reservation_wait is not None:
        payload["reservation_wait"] = dict(reservation_wait)
    canonical_reservation = context.steps.get("canonical_reservation_root")
    if isinstance(canonical_reservation, Mapping) and isinstance(
        canonical_reservation.get("path"), str
    ):
        payload["canonical_reservation_root"] = canonical_reservation["path"]
    artifact_output = context.steps.get("artifact_output_root")
    if isinstance(artifact_output, Mapping) and isinstance(artifact_output.get("path"), str):
        payload["artifact_output_root"] = artifact_output["path"]
    return payload


def _finalize_run(context: RunContext, payload: Mapping[str, Any]) -> dict[str, Any]:
    terminal = dict(payload)
    completed_at = datetime.now(timezone.utc).isoformat()
    terminal.update(
        {
            "run_id": context.run_id,
            "run_started_at": context.started_at,
            "run_completed_at": completed_at,
            "completed_at": completed_at,
            "run_dir": str(context.run_dir.resolve()),
            "status_path": str(context.status_path.resolve()),
            "receipt_path": str(context.receipt_path.resolve()),
            "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
            "finalized": True,
            "subprocesses": dict(context.subprocesses),
        }
    )
    receipt_payload = dict(terminal)
    receipt_payload["receipt_status"] = "complete"
    try:
        _write_immutable_json(context.receipt_path, receipt_payload)
        receipt_sha256 = _file_sha256(context.receipt_path)
    except Exception as exc:  # noqa: BLE001 - receipt failure must fail closed
        failed = dict(terminal)
        reasons = list(failed.get("failure_reasons") or [])
        reasons.append(f"receipt_write_failed:{type(exc).__name__}")
        failed.update(
            {
                "status": "failed",
                "failure_reasons": reasons,
                "receipt_status": "write_failed",
                "receipt_write_error_type": type(exc).__name__,
            }
        )
        _atomic_write_json(context.status_path, failed)
        return failed

    latest = dict(terminal)
    latest.update(
        {
            "receipt_status": "complete",
            "receipt_sha256": receipt_sha256,
        }
    )
    _atomic_write_json(context.status_path, latest)
    return latest


def run(
    *,
    data_root: Path,
    output_root: Path,
    db_path: Path | None = None,
    now: datetime | None = None,
    decision_at: datetime | None = None,
    as_of: date | str | None = None,
    captured_at: datetime | None = None,
    capture_mode: str | None = None,
    calendar_decision_at: datetime | None = None,
    python_executable: str | None = None,
    subprocess_timeout_seconds: int = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    calendar: OfficialTradingCalendar | None = None,
    reservation_wait_seconds: int = SCHEDULED_WRITER_RESERVATION_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    context = _create_run_context(Path(output_root))
    invocation_at = datetime.now(TAIPEI)
    reservation = None
    should_execute_capture = True
    payload: dict[str, Any]
    try:
        reservation_root = _canonical_reservation_root(
            data_root=Path(data_root),
            output_root=Path(output_root),
            db_path=db_path,
        )
        context.steps["canonical_reservation_root"] = {"path": str(reservation_root)}
        context.steps["artifact_output_root"] = {"path": str(Path(output_root).resolve())}
        if subprocess_timeout_seconds <= 0:
            raise ValueError("subprocess_timeout_seconds must be positive")
        if type(reservation_wait_seconds) is not int or not 1 <= reservation_wait_seconds <= SCHEDULED_WRITER_RESERVATION_TIMEOUT_SECONDS:
            raise ValueError("reservation_wait_seconds 必須介於 1 與 10500")
        preflight_clock = _taipei_datetime(now or invocation_at, field_name="now")
        preflight_captured_at = _taipei_datetime(
            captured_at or preflight_clock,
            field_name="captured_at",
        )
        preflight_decision_at = _taipei_datetime(
            decision_at or preflight_captured_at,
            field_name="decision_at",
        )
        preflight_calendar_decision_at, _preflight_as_of, _preflight_basis = (
            _resolve_calendar_decision_at(
                checked_at=preflight_clock,
                resolved_decision_at=preflight_decision_at,
                explicit_decision_at=decision_at,
                as_of=as_of,
                calendar_decision_at=calendar_decision_at,
            )
        )
        calendar_service = calendar or OfficialTradingCalendar(db_path=db_path)
        try:
            preflight_is_open, preflight_calendar_reason = (
                calendar_service.is_official_trading_day(
                    preflight_calendar_decision_at.date()
                )
            )
        except Exception as exc:  # noqa: BLE001 - the inner run records unknown
            preflight_is_open = None
            preflight_calendar_reason = f"calendar_exception:{type(exc).__name__}"

        reservation_wait: Mapping[str, object] | None = None
        execution_now: datetime | None = None
        if preflight_is_open is True:
            day_end = datetime.combine(
                invocation_at.date() + timedelta(days=1),
                datetime.min.time(),
                tzinfo=TAIPEI,
            )
            wait_reserve_seconds = (2 * subprocess_timeout_seconds) + DECISION_CAPTURE_FINALIZATION_RESERVE_SECONDS
            latest_acquire_at = day_end - timedelta(seconds=wait_reserve_seconds)

            def publish_wait_progress(progress: Mapping[str, object]) -> None:
                context.steps["reservation_wait"] = dict(progress)
                _atomic_write_json(
                    context.status_path,
                    {
                        "schema_version": SCHEMA_VERSION,
                        "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
                        "task": TASK_NAME,
                        "run_id": context.run_id,
                        "run_started_at": context.started_at,
                        "status": "waiting_for_heavy_chain_reservation",
                        "status_path": str(context.status_path.resolve()),
                        "receipt_path": str(context.receipt_path.resolve()),
                        "data_root": str(Path(data_root).resolve()),
                        "output_root": str(Path(output_root).resolve()),
                        "canonical_reservation_root": str(reservation_root),
                        "db_path": str(Path(db_path).resolve()) if db_path is not None else None,
                        "reservation_wait": dict(progress),
                        "safety_boundary": {
                            "writes_decision_desk_snapshot": False,
                            "writes_evidence_events": False,
                            "changes_rule_state": False,
                            "changes_advice_state": False,
                            "changes_portfolio_state": False,
                            "broker_execution": False,
                        },
                    },
                )

            try:
                wait_result = wait_for_scheduled_writer_reservation(
                    release_root=reservation_root / "release_v4",
                    timeout_seconds=reservation_wait_seconds,
                    latest_acquire_at=latest_acquire_at,
                    on_progress=publish_wait_progress,
                )
            except ScheduledWriterReservationError as exc:
                context.steps["reservation_wait"] = dict(exc.receipt)
                payload = _exception_payload(context, exc)
                payload.update(
                    {
                        "status": "blocked_reservation_error",
                        "failure_reasons": [
                            f"heavy_chain_reservation_failed:{type(exc.cause).__name__}"
                        ],
                        "reservation_wait": dict(exc.receipt),
                        "canonical_reservation_root": str(reservation_root),
                    }
                )
                return _finalize_run(context, payload)
            reservation_wait = dict(wait_result.receipt)
            context.steps["reservation_wait"] = dict(reservation_wait)
            if wait_result.reservation is None:
                payload = _exception_payload(
                    context,
                    TimeoutError("canonical writer reservation wait timed out"),
                )
                payload.update(
                    {
                        "status": "blocked_reservation_timeout",
                        "failure_reasons": ["heavy_chain_reservation_timeout"],
                        "reservation_wait": dict(reservation_wait),
                        "canonical_reservation_root": str(reservation_root),
                    }
                )
                return _finalize_run(context, payload)
            reservation = wait_result.reservation
            actual_after_acquire = datetime.now(TAIPEI)
            acquire_guard = {
                "checked_at": actual_after_acquire.isoformat(timespec="seconds"),
                "latest_acquire_at": latest_acquire_at.isoformat(timespec="seconds"),
                "completion_reserve_seconds": wait_reserve_seconds,
                "passed": (
                    actual_after_acquire.date() == invocation_at.date()
                    and actual_after_acquire < latest_acquire_at
                ),
            }
            context.steps["reservation_acquire_guard"] = acquire_guard
            if not bool(acquire_guard["passed"]):
                failure_reason = (
                    "heavy_chain_reservation_crossed_taipei_day"
                    if actual_after_acquire.date() != invocation_at.date()
                    else "heavy_chain_reservation_after_completion_cutoff"
                )
                payload = _exception_payload(
                    context,
                    RuntimeError(failure_reason),
                )
                payload.update(
                    {
                        "status": "blocked_reservation_acquire_guard",
                        "failure_reasons": [failure_reason],
                        "reservation_wait": dict(reservation_wait),
                        "reservation_acquire_guard": acquire_guard,
                    }
                )
                should_execute_capture = False
            else:
                execution_now = now if now is not None else actual_after_acquire
        else:
            # Closed/unknown calendar days retain their current no-writer
            # behavior. If the authoritative result changes before execution,
            # _run_once fails closed because no reservation was acquired.
            reservation_wait = {
                "status": "not_acquired",
                "reason": (
                    "official_market_closed"
                    if preflight_is_open is False
                    else "official_market_calendar_unknown"
                ),
                "calendar_reason": preflight_calendar_reason,
            }
            context.steps["reservation_wait"] = dict(reservation_wait)
            execution_now = now

        if should_execute_capture:
            reservation_token = _CHILD_RESERVATION.set(reservation)
            payload = _run_once(
                data_root=data_root,
                output_root=output_root,
                db_path=db_path,
                now=execution_now,
                decision_at=decision_at,
                as_of=as_of,
                captured_at=captured_at,
                capture_mode=capture_mode,
                calendar_decision_at=calendar_decision_at,
                python_executable=python_executable,
                subprocess_timeout_seconds=subprocess_timeout_seconds,
                calendar=calendar,
                reservation_wait=reservation_wait,
                run_context=context,
            )
            if "reservation_acquire_guard" in context.steps:
                payload["reservation_acquire_guard"] = dict(
                    context.steps["reservation_acquire_guard"]
                )
            payload["canonical_reservation_root"] = str(reservation_root)
            payload["artifact_output_root"] = str(Path(output_root).resolve())
    except Exception as exc:  # noqa: BLE001 - persist a terminal failed receipt
        payload = _exception_payload(context, exc)
    finally:
        if "reservation_token" in locals():
            _CHILD_RESERVATION.reset(reservation_token)
        if reservation is not None:
            try:
                release_heavy_chain_reservation(reservation)
            except Exception as exc:  # noqa: BLE001 - lease release is a safety boundary
                if "payload" not in locals():
                    payload = _exception_payload(context, exc)
                payload.update(
                    {
                        "status": "failed_reservation_release",
                        "failure_reasons": [
                            f"heavy_chain_reservation_release_failed:{type(exc).__name__}"
                        ],
                        "reservation_release_error": str(exc),
                    }
                )
    return _finalize_run(context, payload)


def _parse_now(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--now 必須是含時區 ISO timestamp")
    return parsed.astimezone(TAIPEI)


def _parse_decision_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--decision-at 必須是含時區 ISO timestamp")
    return parsed.astimezone(TAIPEI)


def _parse_captured_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--captured-at 必須是含時區 ISO timestamp")
    return parsed.astimezone(TAIPEI)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "保存已通過台北交易日驗證的 Decision Desk 快照與研究型 Evidence Event。"
        )
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(
            os.environ.get("DATA_ROOT", "D:/Min/Python/Project/FA_Data")
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(
            os.environ.get(
                "OUTPUT_ROOT",
                "D:/Min/Python/Project/FA_Data/output",
            )
        ),
    )
    parser.add_argument("--db-path", type=Path)
    parser.add_argument(
        "--now",
        help="測試／重播用的含時區 ISO timestamp；省略時讀取台北現在時間。",
    )
    parser.add_argument(
        "--decision-at",
        help="明確指定含時區的實際決策／評估時間；不會被補成台北 08:30。",
    )
    parser.add_argument(
        "--as-of",
        "--as-of-date",
        dest="as_of",
        help="明確指定來源 as-of 日期；省略時由已到達的台北 08:30 日曆日選取。",
    )
    parser.add_argument(
        "--captured-at",
        help="明確指定含時區的實際 capture 時間；省略時使用 runner checked clock。",
    )
    parser.add_argument(
        "--capture-mode",
        help="研究 capture mode，例如 eod_research；不授予 preopen/natural authority。",
    )
    parser.add_argument(
        "--calendar-decision-at",
        help="可選的台北 08:30 日曆選擇器；與實際 decision_at 分離。",
    )
    parser.add_argument(
        "--subprocess-timeout-seconds",
        type=int,
        default=DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    )
    parser.add_argument("--reservation-wait-seconds", type=int, default=SCHEDULED_WRITER_RESERVATION_TIMEOUT_SECONDS,
                        help="手動重跑的共用鎖等待秒數，1..10500；不跳過鎖或寫入資格。")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = run(
            data_root=args.data_root,
            output_root=args.output_root,
            db_path=args.db_path,
            now=_parse_now(args.now),
            decision_at=_parse_decision_at(args.decision_at),
            as_of=_as_of_date(args.as_of),
            captured_at=_parse_captured_at(args.captured_at),
            capture_mode=args.capture_mode,
            calendar_decision_at=_parse_decision_at(args.calendar_decision_at),
            subprocess_timeout_seconds=args.subprocess_timeout_seconds,
            reservation_wait_seconds=args.reservation_wait_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "task": TASK_NAME,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                # Windows Task Scheduler/redirected cmd may expose cp1252.
                # Console JSON must remain ASCII-safe so a successful capture
                # is not turned into a process failure while printing Chinese.
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            payload,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if payload["status"] in {"passed", "skipped_non_trading_day"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
