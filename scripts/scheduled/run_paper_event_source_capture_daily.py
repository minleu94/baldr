"""在合法台北交易時段持久化 Paper session-open source capture。

這個 caller 由既有 ``baldr-formal-pit-sidecar-postcutoff-daily`` task
於 Pacific 18:00（台北 09:00 PDT／10:00 PST）帶起。它只讀取已凍結的
recommendation queue 與官方 calendar，從 recommendation 內容取得 symbols，
再把同一份 TWSE MIS raw response 以 create-only manifest 保存到 repository
operation root。它不建立 fill、不寫 Paper ledger、不把 quote observation
冒充 broker execution timestamp；EOD Paper writer 會以同一 recommendation
hash 讀回這個 durable capture。
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, time, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile
import time as time_module
import uuid
from urllib.request import Request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.formal_runtime_config import (  # noqa: E402
    FORMAL_RUNTIME_CONFIG_ENV,
    FormalRuntimeConfigError,
    load_optional_formal_runtime_config,
)
from data_module.official_trading_calendar import OfficialTradingCalendar  # noqa: E402
from data_module.paper_daily_execution_producer import (  # noqa: E402
    PaperExecutionProducerError,
    TAIPEI,
    _load_recommendation,
    next_proven_trading_day,
    resolve_pending_recommendation,
)
from data_module.paper_event_source_capture import (  # noqa: E402
    DEFAULT_TIMEOUT_SECONDS,
    PAPER_EVENT_CAPTURE_ATTEMPT_SCHEMA_VERSION,
    PAPER_EXECUTION_EVENT_CAPTURE_MAX_BYTES,
    PaperEventSourceCaptureError,
    capture_twse_session_open_prices_for_recommendation,
)


TASK_NAME = "baldr-paper-event-source-capture-daily"
DEFAULT_DATA_ROOT = Path(r"F:\Min\Python\Project\FA_Data")
OPERATIONAL_ROOT = ROOT / "output" / "paper_execution_eod_replay"
RECOMMENDATION_ROOT = DEFAULT_DATA_ROOT / "output" / "recommendation" / "runs"
MARKET_DB = DEFAULT_DATA_ROOT / "sqlite" / "twstock.db"
EVENT_CAPTURE_ROOT = OPERATIONAL_ROOT / "event_captures"
RECEIPT_ROOT = OPERATIONAL_ROOT / "receipts"
STATUS_ROOT = OPERATIONAL_ROOT / "scheduled" / "paper_event_source_capture"
CALENDAR_CACHE_ROOT = OPERATIONAL_ROOT / "calendar_cache"
SESSION_OPEN = time(9, 0)
SESSION_CLOSE = time(13, 30)
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 30


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _write_status(path: Path, payload: Mapping[str, object]) -> None:
    """以同目錄 replace 更新觀測 pointer，避免讀到半份 status。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (_canonical_json(dict(payload)) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _runtime_projection(
    runtime_config: Mapping[str, object] | None,
    *,
    error: str | None = None,
) -> dict[str, object]:
    if runtime_config is not None:
        return dict(runtime_config)
    return {
        "status": "invalid" if error is not None else "absent",
        "environment_variable": FORMAL_RUNTIME_CONFIG_ENV,
        "error": error,
    }


def _base(
    *,
    observed: datetime,
    status_path: Path,
    runtime_config: Mapping[str, object] | None,
    recommendation_root: Path,
    market_db: Path,
    durable_root: Path,
    receipt_root: Path,
    runtime_error: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "paper-event-source-capture-scheduled.v1",
        "task": TASK_NAME,
        "producer": "scripts.scheduled.run_paper_event_source_capture_daily",
        "observed_at": observed.isoformat(),
        "decision_timezone": "Asia/Taipei",
        "status_path": str(status_path.expanduser().resolve()),
        "recommendation_root": str(recommendation_root.expanduser().resolve()),
        "market_db": str(market_db.expanduser().resolve()),
        "durable_root": str(durable_root.expanduser().resolve()),
        "receipt_root": str(receipt_root.expanduser().resolve()),
        "session_window": {
            "timezone": "Asia/Taipei",
            "start": SESSION_OPEN.isoformat(),
            "end_exclusive": SESSION_CLOSE.isoformat(),
            "source_capture_schedule": "Pacific 18:00 daily via PIT sidecar action",
        },
        "formal_runtime_config": _runtime_projection(
            runtime_config,
            error=runtime_error,
        ),
        "candidate_only": True,
        "research_only": True,
        "execution_event_time_proven": False,
        "formal_eligible": False,
        "formal_ready": False,
        "formal_credit": False,
        "broker_order_allowed": False,
        "broker_execution": False,
        "writes_market_database": False,
        "writes_paper_ledger": False,
        "historical_backfill_claimed": False,
        "source_capture_only": True,
    }


def _calendar_state(
    calendar: OfficialTradingCalendar,
    target_date: date,
) -> tuple[str, str]:
    open_value, reason = calendar.is_official_trading_day(target_date)
    reason_text = str(reason)
    if open_value:
        return "open", reason_text
    lowered = reason_text.casefold()
    unknown_markers = (
        "unknown",
        "missing",
        "unavailable",
        "blocked",
        "invalid",
        "insufficient",
        "not_loaded",
        "not_loaded",
    )
    if any(marker in lowered for marker in unknown_markers):
        return "unknown", reason_text
    return "closed", reason_text


def _new_capture_temp_root(execution_date: date) -> Path:
    """回傳尚未建立的 TEMP 目錄，讓 capture writer 自己做 create-only mkdir。"""

    temp_root = Path(tempfile.gettempdir())
    for _ in range(20):
        candidate = temp_root / (
            f"paper_event_capture_{execution_date.isoformat()}_{uuid.uuid4().hex[:12]}"
        )
        if not candidate.exists():
            return candidate
    raise RuntimeError("Paper event capture TEMP directory collision")


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _write_create_only_diagnostic_file(path: Path, raw: bytes) -> str:
    """以同目錄暫存檔與 hard-link 建立不可覆寫的失敗診斷檔。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem[:24]}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    descriptor_open = True
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor_open = False
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    except FileExistsError as error:
        raise PaperEventSourceCaptureError(
            f"capture diagnostic file already exists:{path.name}"
        ) from error
    except OSError as error:
        raise PaperEventSourceCaptureError(
            f"capture diagnostic file publish failed:{path.name}"
        ) from error
    finally:
        if descriptor_open:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError as error:
            raise PaperEventSourceCaptureError(
                f"capture diagnostic temporary cleanup failed:{path.name}"
            ) from error
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _persist_failed_capture_diagnostic(
    *,
    temp_root: Path,
    status_root: Path,
    execution_date: date,
    attempt: int,
    error: BaseException,
) -> dict[str, object]:
    """將失敗 attempt 的 bounded raw 與 receipt 隔離保存到 scheduler status。"""

    source_receipt_path = temp_root / "capture_attempt.json"
    receipt: dict[str, object]
    if source_receipt_path.is_file():
        encoded_receipt = source_receipt_path.read_bytes()
        if len(encoded_receipt) > 128 * 1024:
            raise PaperEventSourceCaptureError(
                "capture attempt receipt 超過診斷上限"
            )
        loaded = json.loads(encoded_receipt.decode("utf-8"))
        if not isinstance(loaded, dict):
            raise PaperEventSourceCaptureError(
                "capture attempt receipt 必須是 JSON object"
            )
        receipt = dict(loaded)
    else:
        error_receipt = getattr(error, "attempt_receipt", None)
        if isinstance(error_receipt, Mapping):
            receipt = dict(error_receipt)
        else:
            receipt = {
                "schema_version": PAPER_EVENT_CAPTURE_ATTEMPT_SCHEMA_VERSION,
                "request": {
                    "attempted": None,
                    "method": None,
                    "url": None,
                    "headers": None,
                },
                "request_started_at": None,
                "request_completed_at": None,
                "response": None,
                "raw_response": {
                    "present": False,
                    "path": None,
                    "type": None,
                    "bytes": None,
                    "sha256": None,
                    "exceeded_limit": None,
                },
                "parser": {
                    "version": None,
                    "status": "not_attempted",
                    "failure_reason": None,
                },
            }

    temporary_raw_path = temp_root / "raw_response.bin"
    raw: bytes | None = None
    if temporary_raw_path.is_file():
        with temporary_raw_path.open("rb") as stream:
            raw = stream.read(PAPER_EXECUTION_EVENT_CAPTURE_MAX_BYTES + 1)
        if len(raw) > PAPER_EXECUTION_EVENT_CAPTURE_MAX_BYTES + 1:
            raise PaperEventSourceCaptureError(
                "capture diagnostic raw response 超過 bounded 上限"
            )

    raw_hash = (
        None if raw is None else "sha256:" + hashlib.sha256(raw).hexdigest()
    )
    raw_meta_value = receipt.get("raw_response")
    raw_meta = raw_meta_value if isinstance(raw_meta_value, Mapping) else {}
    if raw is not None:
        if raw_meta.get("present") is False:
            raise PaperEventSourceCaptureError(
                "capture attempt receipt 與 raw response 存在狀態不一致"
            )
        if raw_meta.get("sha256") not in {None, raw_hash}:
            raise PaperEventSourceCaptureError(
                "capture attempt receipt raw SHA-256 不一致"
            )
        if raw_meta.get("bytes") not in {None, len(raw)}:
            raise PaperEventSourceCaptureError(
                "capture attempt receipt raw bytes 不一致"
            )
    elif raw_meta.get("present") is True:
        raise PaperEventSourceCaptureError(
            "capture attempt receipt 指定的 raw response 不存在"
        )

    status_base = status_root.expanduser().resolve()
    diagnostic_parent = status_base / "capture_attempt_diagnostics"
    date_parent = diagnostic_parent / execution_date.isoformat()
    diagnostic_dir = date_parent / f"attempt-{attempt:02d}-{uuid.uuid4().hex}"
    for candidate in (diagnostic_parent, date_parent, diagnostic_dir):
        try:
            candidate.relative_to(status_base)
        except ValueError as path_error:
            raise PaperEventSourceCaptureError(
                "capture diagnostic path escaped status root"
            ) from path_error
        if _is_reparse_point(candidate):
            raise PaperEventSourceCaptureError(
                "capture diagnostic path contains symlink or junction"
            )
        candidate.mkdir(parents=True, exist_ok=True)

    raw_file_name = "raw_response.bin" if raw is not None else None
    if raw is not None:
        _write_create_only_diagnostic_file(
            diagnostic_dir / "raw_response.bin",
            raw,
        )
    archived_receipt = dict(receipt)
    archived_receipt["scheduled_attempt"] = {
        "attempt": attempt,
        "status": "failed",
        "failure_type": type(error).__name__,
        "failure_reason": str(error),
    }
    archived_receipt["diagnostic_artifacts"] = {
        "raw_response_file": raw_file_name,
        "raw_response_sha256": raw_hash,
        "raw_response_bytes": None if raw is None else len(raw),
    }
    receipt_raw = (_canonical_json(archived_receipt) + "\n").encode("utf-8")
    receipt_hash = _write_create_only_diagnostic_file(
        diagnostic_dir / "attempt_receipt.json",
        receipt_raw,
    )
    return {
        "diagnostic_directory": str(diagnostic_dir.resolve()),
        "attempt_receipt_path": str(
            (diagnostic_dir / "attempt_receipt.json").resolve()
        ),
        "attempt_receipt_sha256": receipt_hash,
        "raw_response_path": (
            None
            if raw_file_name is None
            else str((diagnostic_dir / raw_file_name).resolve())
        ),
        "raw_response_sha256": raw_hash,
        "raw_response_bytes": None if raw is None else len(raw),
    }


def _cleanup_capture_temp_root(temp_root: Path) -> tuple[str, str | None]:
    try:
        if temp_root.exists():
            shutil.rmtree(temp_root)
    except OSError as error:
        return "preserved", f"{type(error).__name__}:{error}"
    return ("removed" if not temp_root.exists() else "preserved"), None


def _is_transient_capture_error(error: BaseException) -> bool:
    """只重試尚未形成 durable bytes 的官方暫時來源失敗。"""

    lowered = str(error).casefold()
    transient_markers = (
        "twse mis bounded get 失敗",
        "twse mis http status 不是 200",
        "twse mis response bytes 為空",
        "market_source_capture_raw_response_status_invalid",
        "market_source_capture_raw_response_message_invalid",
        "market_source_capture_raw_response_rows_missing",
        "market_source_capture_raw_response_session_open_not_ready",
    )
    terminal_markers = (
        "identity",
        "hash",
        "manifest",
        "junction",
        "symlink",
        "path",
        "execution_date",
        "outside_session",
        "content mismatch",
    )
    if any(marker in lowered for marker in terminal_markers):
        return False
    return any(marker in lowered for marker in transient_markers)


def run_capture(
    *,
    now: datetime | None = None,
    recommendation_root: Path = RECOMMENDATION_ROOT,
    market_db: Path = MARKET_DB,
    durable_root: Path = EVENT_CAPTURE_ROOT,
    receipt_root: Path = RECEIPT_ROOT,
    status_root: Path = STATUS_ROOT,
    calendar: OfficialTradingCalendar | None = None,
    runtime_config: Mapping[str, object] | None = None,
    load_runtime: bool = True,
    fetcher: Callable[[Request, float], object] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_delay_seconds: int = DEFAULT_RETRY_DELAY_SECONDS,
    allowed_durable_root: Path | None = None,
) -> tuple[dict[str, object], int]:
    """執行一次 bounded capture；測試可注入 clock/calendar/fetcher。"""

    if isinstance(max_attempts, bool) or not 1 <= max_attempts <= 3:
        raise ValueError("max_attempts 必須介於 1..3")
    if isinstance(retry_delay_seconds, bool) or not 0 <= retry_delay_seconds <= 300:
        raise ValueError("retry_delay_seconds 必須介於 0..300 秒")
    observed_value = now or datetime.now(timezone.utc)
    if observed_value.tzinfo is None or observed_value.utcoffset() is None:
        raise ValueError("now 必須帶時區")
    observed = observed_value.astimezone(timezone.utc)
    status_path = status_root.expanduser().resolve() / "latest_status.json"
    calendar_value = calendar or OfficialTradingCalendar(
        db_path=market_db,
        calendar_cache_path=CALENDAR_CACHE_ROOT,
        temporary_closure_path=CALENDAR_CACHE_ROOT,
    )
    local = observed.astimezone(TAIPEI)
    calendar_status, calendar_reason = _calendar_state(calendar_value, local.date())
    runtime_error: str | None = None
    if load_runtime and calendar_status == "open":
        try:
            runtime_config = load_optional_formal_runtime_config(
                role="paper_eod_wrapper",
                observed=observed,
            )
        except FormalRuntimeConfigError as error:
            runtime_error = str(error)
    base = _base(
        observed=observed,
        status_path=status_path,
        runtime_config=runtime_config,
        recommendation_root=recommendation_root,
        market_db=market_db,
        durable_root=durable_root,
        receipt_root=receipt_root,
        runtime_error=runtime_error,
    )
    base["retry_policy"] = {
        "max_attempts": max_attempts,
        "retry_delay_seconds": retry_delay_seconds,
        "same_frozen_recommendation_required": True,
        "same_taipei_session_required": True,
        "retryable_failures": "official_transient_get_or_empty_response_or_verified_opening_not_ready",
        "terminal_failures": "identity/hash/path/schema/capture-custody violations",
    }
    base["taipei_now"] = local.isoformat()
    base["calendar"] = {
        "date": local.date().isoformat(),
        "status": calendar_status,
        "reason": calendar_reason,
    }
    if calendar_status == "unknown":
        payload = {
            **base,
            "status": "blocked",
            "blockers": ["official_calendar_evidence_unknown:" + calendar_reason],
        }
        _write_status(status_path, payload)
        return payload, 2
    if calendar_status == "closed":
        payload = {
            **base,
            "status": "skipped_non_trading_day",
            "reason": calendar_reason,
            "blockers": [],
        }
        _write_status(status_path, payload)
        return payload, 0
    if runtime_error is not None:
        payload = {
            **base,
            "status": "blocked",
            "blockers": [f"runtime_config_invalid:{runtime_error}"],
        }
        _write_status(status_path, payload)
        return payload, 2
    if load_runtime and runtime_config is None:
        payload = {
            **base,
            "status": "blocked",
            "blockers": ["runtime_config_missing_for_paper_event_capture"],
        }
        _write_status(status_path, payload)
        return payload, 2
    if runtime_config is not None and runtime_config.get("activation_status") != "active":
        payload = {
            **base,
            "status": "waiting_for_runtime_config",
            "blockers": [
                "runtime_config_waiting_for_activation:"
                f"{runtime_config.get('activation_trading_day')}"
            ],
        }
        _write_status(status_path, payload)
        return payload, 2

    recommendation_root = recommendation_root.expanduser().resolve()
    market_db = market_db.expanduser().resolve()
    durable_root = durable_root.expanduser().resolve()
    allowed_root = (
        allowed_durable_root or OPERATIONAL_ROOT
    ).expanduser().resolve()
    receipt_root = receipt_root.expanduser().resolve()
    if not recommendation_root.is_dir():
        payload = {
            **base,
            "status": "blocked",
            "blockers": [f"recommendation_root_missing:{recommendation_root}"],
        }
        _write_status(status_path, payload)
        return payload, 2
    window_time = local.timetz().replace(tzinfo=None)
    if not SESSION_OPEN <= window_time < SESSION_CLOSE:
        payload = {
            **base,
            "status": "waiting_for_paper_session_window",
            "blockers": [
                "paper_event_capture_window_is_"
                + ("not_started" if window_time < SESSION_OPEN else "closed")
            ],
        }
        _write_status(status_path, payload)
        return payload, 2

    try:
        selected, selection_reason = resolve_pending_recommendation(
            recommendation_root,
            observed=observed,
            market_db=market_db,
            calendar=calendar_value,
            receipt_root=receipt_root,
        )
    except (OSError, PaperExecutionProducerError, ValueError, sqlite3.Error) as error:
        payload = {
            **base,
            "status": "blocked",
            "blockers": [
                f"recommendation_queue_resolution_failed:{type(error).__name__}:{error}"
            ],
        }
        _write_status(status_path, payload)
        return payload, 2
    base["queue_selection"] = {
        "selected_path": None if selected is None else str(selected.resolve()),
        "reason": selection_reason,
        "source_mode": "same_persistent_frozen_recommendation_as_paper_eod",
    }
    if selected is None:
        payload = {
            **base,
            "status": "waiting_for_frozen_recommendation",
            "blockers": ["paper_event_capture_recommendation_missing:" + selection_reason],
        }
        _write_status(status_path, payload)
        return payload, 2

    try:
        recommendation = _load_recommendation(selected, observed=observed)
        next_day = next_proven_trading_day(
            recommendation.decision_date,
            market_db=market_db,
            calendar=calendar_value,
        )
        if next_day.get("status") != "ready" or not next_day.get("date"):
            raise PaperExecutionProducerError(
                str(next_day.get("reason") or "next official execution date unproven")
            )
        execution_date = date.fromisoformat(str(next_day["date"]))
        if execution_date != local.date():
            raise PaperExecutionProducerError(
                "queue selected recommendation execution date differs from current Taipei date:"
                f"{execution_date.isoformat()}!={local.date().isoformat()}"
            )
        capture_attempts: list[dict[str, object]] = []
        base["capture_attempts"] = capture_attempts
        capture: dict[str, object] | None = None
        for attempt in range(1, max_attempts + 1):
            temp_root = _new_capture_temp_root(execution_date)
            try:
                capture = capture_twse_session_open_prices_for_recommendation(
                    recommendation_path=selected,
                    execution_date=execution_date,
                    output_dir=temp_root,
                    durable_root=durable_root,
                    allowed_durable_root=allowed_root,
                    # In production ``now`` is deliberately omitted so the
                    # capture producer records actual HTTP completion.  A
                    # supplied ``run_capture(now=...)`` remains a test clock.
                    now=observed if now is not None else None,
                    timeout_seconds=timeout_seconds,
                    fetcher=fetcher,
                    expected_recommendation_file_hash=recommendation.file_hash,
                    expected_recommendation_content_hash=recommendation.content_hash,
                    venue_source_output_root=(
                        market_db.parent.parent / "output"
                        if now is None and fetcher is None else None
                    ),
                )
                successful_attempt: dict[str, object] = {
                    "attempt": attempt,
                    "status": "succeeded",
                    "temporary_capture_root": str(temp_root),
                    "temporary_cleanup": "pending",
                }
                attempt_receipt = capture.get("attempt_receipt")
                if isinstance(attempt_receipt, Mapping):
                    successful_attempt["request_attempt"] = dict(attempt_receipt)
                capture_attempts.append(successful_attempt)
                break
            except (
                OSError,
                PaperEventSourceCaptureError,
                PaperExecutionProducerError,
                ValueError,
                TypeError,
            ) as error:
                retryable = _is_transient_capture_error(error)
                failed_attempt: dict[str, object] = {
                    "attempt": attempt,
                    "status": "failed",
                    "retryable": retryable,
                    "reason": f"{type(error).__name__}:{error}",
                    "temporary_capture_root": str(temp_root),
                }
                try:
                    diagnostic = _persist_failed_capture_diagnostic(
                        temp_root=temp_root,
                        status_root=status_root,
                        execution_date=execution_date,
                        attempt=attempt,
                        error=error,
                    )
                except (OSError, PaperEventSourceCaptureError, ValueError, TypeError) as diagnostic_error:
                    failed_attempt.update(
                        {
                            "diagnostic_status": "failed",
                            "diagnostic_error": (
                                f"{type(diagnostic_error).__name__}:"
                                f"{diagnostic_error}"
                            ),
                            "temporary_cleanup": "preserved",
                        }
                    )
                    capture_attempts.append(failed_attempt)
                    raise PaperEventSourceCaptureError(
                        "capture diagnostic persistence failed; "
                        f"source_error={type(error).__name__}:{error}; "
                        f"diagnostic_error={type(diagnostic_error).__name__}:"
                        f"{diagnostic_error}"
                    ) from error
                failed_attempt.update(
                    {
                        **diagnostic,
                        "diagnostic_status": "saved",
                    }
                )
                cleanup_status, cleanup_error = _cleanup_capture_temp_root(temp_root)
                failed_attempt["temporary_cleanup"] = cleanup_status
                if cleanup_status != "removed" and cleanup_error is None:
                    cleanup_error = "temporary capture root remains after cleanup attempt"
                if cleanup_error is not None:
                    failed_attempt["temporary_cleanup_error"] = cleanup_error
                capture_attempts.append(failed_attempt)
                if not retryable or attempt >= max_attempts:
                    raise
                if retry_delay_seconds:
                    time_module.sleep(retry_delay_seconds)
        if capture is None:  # pragma: no cover - loop either returns or raises
            raise PaperEventSourceCaptureError("capture attempts produced no result")
        base["capture_attempts"] = capture_attempts
    except (
        OSError,
        PaperEventSourceCaptureError,
        PaperExecutionProducerError,
        ValueError,
        TypeError,
    ) as error:
        attempts_value = base.get("capture_attempts", [])
        attempts = attempts_value if isinstance(attempts_value, list) else []
        cleanup_values = [
            item.get("temporary_cleanup")
            for item in attempts
            if isinstance(item, Mapping)
        ]
        cleanup_errors = [
            {
                "attempt": item.get("attempt"),
                "temporary_capture_root": item.get("temporary_capture_root"),
                "error": item.get("temporary_cleanup_error")
                or "temporary capture root remains after cleanup attempt",
            }
            for item in attempts
            if isinstance(item, Mapping)
            and item.get("temporary_cleanup") != "removed"
        ]
        if not cleanup_values:
            temporary_cleanup = "not_applicable"
        elif all(value == "removed" for value in cleanup_values):
            temporary_cleanup = "removed_after_diagnostic_persist"
        elif any(value == "removed" for value in cleanup_values):
            temporary_cleanup = "partial_failure"
        else:
            temporary_cleanup = "preserved"
        cleanup_blockers = [
            "capture_temp_cleanup_failed:"
            f"attempt-{item['attempt']}:{item['error']}"
            for item in cleanup_errors
        ]
        payload = {
            **base,
            "status": "blocked",
            "blockers": [
                f"paper_event_source_capture_failed:{type(error).__name__}:{error}"
            ]
            + cleanup_blockers,
            "durable_capture": False,
            "capture_attempts": attempts,
            "temporary_cleanup": temporary_cleanup,
            "temporary_cleanup_errors": cleanup_errors,
            "failed_attempt_diagnostics": [
                item.get("diagnostic_directory")
                for item in attempts
                if isinstance(item, Mapping)
                and item.get("diagnostic_status") == "saved"
            ],
            "preserved_temporary_capture_roots": [
                item.get("temporary_capture_root")
                for item in attempts
                if isinstance(item, Mapping)
                and item.get("temporary_cleanup") == "preserved"
            ],
        }
        _write_status(status_path, payload)
        return payload, 2

    temp_cleanup_error: str | None = None
    try:
        shutil.rmtree(temp_root)
    except FileNotFoundError:
        pass
    except OSError as error:
        temp_cleanup_error = f"{type(error).__name__}:{error}"
    temp_cleaned = not temp_root.exists()
    if not temp_cleaned and temp_cleanup_error is None:
        temp_cleanup_error = "temporary capture root remains after cleanup attempt"
    if capture_attempts:
        capture_attempts[-1]["temporary_cleanup"] = (
            "removed" if temp_cleaned else "preserved"
        )
        if temp_cleanup_error is not None:
            capture_attempts[-1]["temporary_cleanup_error"] = temp_cleanup_error
    cleanup_errors = [
        {
            "attempt": item.get("attempt"),
            "temporary_capture_root": item.get("temporary_capture_root"),
            "error": item.get("temporary_cleanup_error"),
        }
        for item in capture_attempts
        if isinstance(item, Mapping)
        and item.get("temporary_cleanup") != "removed"
    ]
    cleanup_states = [
        item.get("temporary_cleanup")
        for item in capture_attempts
        if isinstance(item, Mapping)
    ]
    if not cleanup_states or all(value == "removed" for value in cleanup_states):
        overall_temporary_cleanup = "removed"
    elif all(value != "removed" for value in cleanup_states):
        overall_temporary_cleanup = "preserved"
    else:
        overall_temporary_cleanup = "partial_failure"
    cleanup_blockers = [
        "capture_temp_cleanup_failed:"
        f"attempt-{item['attempt']}:{item['error']}"
        for item in cleanup_errors
    ]
    preserved_temp_roots = [
        item.get("temporary_capture_root")
        for item in capture_attempts
        if isinstance(item, Mapping)
        and item.get("temporary_cleanup") == "preserved"
    ]
    cleanup_failed = bool(cleanup_errors)
    payload = {
        **base,
        "status": "blocked" if cleanup_failed else "source_capture_durable",
        "capture_status": "source_capture_durable",
        "execution_date": capture.get("execution_date"),
        "recommendation": capture.get("recommendation"),
        "durable_capture": capture.get("durable_capture"),
        "manifest_path": capture.get("manifest_path"),
        "manifest_file_hash": capture.get("manifest_file_hash"),
        "raw_response_hash": capture.get("raw_response_hash"),
        "capture_file_hash": capture.get("capture_file_hash"),
        "durable_readback_verified": capture.get("durable_readback_verified") is True,
        "idempotent_replay": capture.get("idempotent_replay") is True,
        "capture_attempts": base.get("capture_attempts", []),
        "temporary_capture_root": str(temp_root),
        "temporary_cleanup": overall_temporary_cleanup,
        "temporary_cleanup_error": temp_cleanup_error,
        "temporary_cleanup_errors": cleanup_errors,
        "preserved_temporary_capture_roots": preserved_temp_roots,
        "blockers": cleanup_blockers,
        "formal_credit": False,
    }
    _write_status(status_path, payload)
    return payload, 2 if cleanup_failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(
        description="在合法台北交易時段擷取已凍結 Paper recommendation 的開盤來源。"
    ).parse_args(argv)
    try:
        result, exit_code = run_capture()
    except Exception as error:  # noqa: BLE001 - scheduled boundary is fail closed
        observed = datetime.now(timezone.utc)
        status_path = STATUS_ROOT / "latest_status.json"
        result = {
            **_base(
                observed=observed,
                status_path=status_path,
                runtime_config=None,
                recommendation_root=RECOMMENDATION_ROOT,
                market_db=MARKET_DB,
                durable_root=EVENT_CAPTURE_ROOT,
                receipt_root=RECEIPT_ROOT,
                runtime_error=None,
            ),
            "status": "blocked",
            "blockers": [
                f"paper_event_source_capture_uncaught:{type(error).__name__}:{error}"
            ],
        }
        _write_status(status_path, result)
        exit_code = 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EVENT_CAPTURE_ROOT",
    "MARKET_DB",
    "OPERATIONAL_ROOT",
    "RECOMMENDATION_ROOT",
    "RECEIPT_ROOT",
    "STATUS_ROOT",
    "run_capture",
]
