"""Run the normal daily recommendation-to-learning shadow pipeline.

This is the 05:45 entrypoint.  It keeps the official event refresh,
technical/source custody, recommendation snapshot, and calibration learning
on one durable output root.  Optional MoneyDJ broker pages remain outside the
core lane; every other dependency is reported explicitly and the learning
step never receives caller-supplied symbols unless the operator asks for it.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
# Task Scheduler 以 file path 執行本檔時，sys.path[0] 只有 scripts\scheduled；
# 先綁定 repository root，讓 CLI 與 package／pytest import 使用同一個內部模組邊界。
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TAIPEI = ZoneInfo("Asia/Taipei")
TASK_NAME = "baldr-recommendation-calibration-learning-daily"
_MAX_SNAPSHOT_INVOCATION_STDOUT_BYTES = 8 * 1024 * 1024
_SNAPSHOT_INVOCATION_STDOUT_NAME = "recommendation_snapshot.stdout.bin"

from app_module.recommendation.queries import _read_regular_file_no_follow  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--source-db", type=Path)
    parser.add_argument("--max-stocks", type=int, default=200)
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--history-start-date", default="2014-01-01")
    parser.add_argument("--max-decision-dates", type=int, default=100)
    parser.add_argument("--fixed-round-trip-cost-bp", type=int, default=50)
    parser.add_argument(
        "--cost-scenario",
        choices=("legacy_fixed_bp", "banktaiwan_estimated_research"),
        default="legacy_fixed_bp",
        help="成本 contract；預設維持既有 fixed 50bp，臺銀情境僅供 research/shadow。",
    )
    parser.add_argument("--cost-policy-estimate-date", default="2026-01-01")
    parser.add_argument("--research-order-amount-twd", default=None)
    parser.add_argument("--research-order-quantity-shares", type=int, default=None)
    parser.add_argument(
        "--research-order-lot-type",
        choices=("full_lot", "odd_lot"),
        default="full_lot",
    )
    parser.add_argument(
        "--research-instrument-type",
        choices=("ordinary_stock", "equity_etf"),
        default="ordinary_stock",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="optional explicit cohort for a controlled trial; omitted for the normal snapshot cohort",
    )
    parser.add_argument("--official-timeout-seconds", type=int, default=30)
    parser.add_argument("--official-max-attempts", type=int, default=4)
    parser.add_argument("--official-retry-delay-seconds", type=int, default=2)
    parser.add_argument("--official-request-delay-seconds", type=int, default=1)
    parser.add_argument("--window-weekdays", type=int, default=10)
    parser.add_argument(
        "--calendar-cache-path",
        type=Path,
        help="annual TWSE calendar cache forwarded to the quick updater",
    )
    parser.add_argument(
        "--temporary-closure-path",
        type=Path,
        help="official temporary-closure cache forwarded to the quick updater",
    )
    parser.add_argument("--daily-delay-seconds", type=float, default=0.5)
    parser.add_argument("--tpex-delay-seconds", type=float, default=0.5)
    parser.add_argument("--broker-delay-seconds", type=float, default=0.5)
    parser.add_argument(
        "--child-timeout-seconds",
        type=float,
        default=3600.0,
        help="hard timeout for each subprocess; a timeout leaves durable receipts untouched",
    )
    parser.add_argument(
        "--pipeline-timeout-seconds",
        type=float,
        default=7200.0,
        help="hard wall-clock budget for all subprocesses in this daily run",
    )
    parser.add_argument(
        "--skip-technical-refresh",
        action="store_true",
        help="only for an already verified same-day technical receipt; status records the skip",
    )
    return parser


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _write_terminal_receipt(
    path: Path,
    payload: Mapping[str, Any],
) -> str:
    """以 create-only、flush／fsync 寫入一次 immutable pipeline receipt。"""

    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _terminal_receipt_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    """保留 bounded terminal 摘要，避免把 child stdout／完整 payload 複製進 receipt。"""

    def bounded_messages(value: object) -> list[str]:
        if not isinstance(value, (list, tuple)):
            return []
        return [str(item)[:500] for item in list(value)[:32]]

    steps = payload.get("steps")
    step_projection: dict[str, dict[str, Any]] = {}
    if isinstance(steps, Mapping):
        for name, value in steps.items():
            if not isinstance(value, Mapping):
                continue
            step_projection[str(name)] = {
                "status": value.get("status"),
                "returncode": value.get("returncode"),
                "recoverable": value.get("recoverable"),
                "child_stdout_artifact_path": value.get("child_stdout_artifact_path"),
                "child_stdout_artifact_size": value.get("child_stdout_artifact_size"),
                "child_stdout_sha256": value.get("child_stdout_sha256"),
            }
    return {
        "schema_version": "daily-recommendation-learning-terminal-receipt.v1",
        "task": payload.get("task"),
        "run_id": payload.get("run_id"),
        "decision_date": payload.get("decision_date"),
        "decision_timezone": payload.get("decision_timezone"),
        "status": payload.get("status"),
        "completed_at": payload.get("completed_at"),
        "failure_stage": payload.get("failure_stage"),
        "error_type": payload.get("error_type"),
        "error": payload.get("error"),
        "blockers": bounded_messages(payload.get("blockers")),
        "warnings": bounded_messages(payload.get("warnings")),
        "steps": step_projection,
        "status_path": payload.get("status_path"),
        "log_path": payload.get("log_path"),
        "terminal": True,
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _status_path(output_root: Path, name: str) -> Path:
    if name == "recommendation_learning":
        return output_root / "recommendation_learning" / "latest_status.json"
    return output_root / "scheduled" / name / "latest_status.json"


def _same_path(value: object, expected: Path) -> bool:
    if not isinstance(value, (str, os.PathLike)):
        return False
    try:
        return Path(value).expanduser().resolve() == expected
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def _iso_date(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        return None


def _aware_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _technical_window_matches_decision(
    hint: Mapping[str, Any],
    *,
    decision_date: str,
    now: datetime,
) -> bool:
    if hint.get("status") != "ready":
        return False
    start = _iso_date(hint.get("source_date_start"))
    end = _iso_date(hint.get("source_date_end"))
    if not start or not end or start > end or end != decision_date:
        return False
    available_at = _aware_datetime(hint.get("available_at"))
    if available_at is None or available_at > now:
        return False
    return available_at.astimezone(TAIPEI).date().isoformat() == decision_date


def _technical_child_plan(
    *,
    data_root: Path,
    source_db: Path,
    source_date_start: str,
    source_date_end: str,
) -> dict[str, Any]:
    """解析 technical canonical routing，不把正常 refresh 綁成 receipt 前置條件。"""

    formal_output_root = (data_root / "output").resolve()
    expected_source_db = (data_root / "sqlite" / "twstock.db").resolve()
    status_path = _status_path(formal_output_root, "data_update_quick")
    plan: dict[str, Any] = {
        "status": "blocked",
        "name": "data_update_quick",
        "formal_output_root": str(formal_output_root),
        "status_path": str(status_path),
        "source_db": str(source_db),
        "expected_source_db": str(expected_source_db),
        "source_date_start": source_date_start,
        "source_date_end": source_date_end,
    }
    if source_db != expected_source_db:
        plan.update(
            {
                "reason": "technical_source_db_mismatch",
                "message": (
                    "technical child is blocked because source_db does not match "
                    "the quick runner's data-root SQLite database"
                ),
            }
        )
        return plan
    plan["status"] = "ready"
    plan["reason"] = "canonical_formal_technical_root_ready"
    return plan


def _formal_receipt_window_hint(*, data_root: Path, source_db: Path) -> dict[str, Any]:
    """讀取 bounded formal window hint；最終驗證仍由 quick 既有 verifier 負責。"""

    formal_output_root = (data_root / "output").resolve()
    status_path = _status_path(formal_output_root, "data_update_quick")
    base = {
        "status": "unavailable",
        "formal_output_root": str(formal_output_root),
        "status_path": str(status_path),
        "source_db": str(source_db),
    }
    status = _read_json(status_path)
    if not isinstance(status, Mapping):
        base["reason"] = "formal_quick_status_unreadable"
        return base
    for field in ("data_root", "output_root", "formal_output_root"):
        value = status.get(field)
        if value is not None and not _same_path(
            value,
            data_root if field == "data_root" else formal_output_root,
        ):
            base["reason"] = f"formal_quick_{field}_mismatch"
            return base
    publication = status.get("technical_publication_receipt")
    if not isinstance(publication, Mapping) or publication.get("status") != "published":
        base["reason"] = "formal_technical_publication_missing"
        return base
    source_date_start = publication.get("source_date_start")
    source_date_end = publication.get("source_date_end")
    receipt_path = publication.get("receipt_path")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (source_date_start, source_date_end, receipt_path)
    ):
        base["reason"] = "formal_technical_receipt_pointer_incomplete"
        return base
    resolved_receipt = Path(str(receipt_path)).expanduser()
    if not resolved_receipt.is_absolute():
        resolved_receipt = formal_output_root / resolved_receipt
    try:
        resolved_receipt = resolved_receipt.resolve()
    except (OSError, RuntimeError):
        base["reason"] = "formal_technical_receipt_path_unresolvable"
        return base
    if not resolved_receipt.is_relative_to(formal_output_root):
        base["reason"] = "formal_technical_receipt_path_unauthorized"
        return base
    return {
        **base,
        "status": "ready",
        "reason": "formal_technical_receipt_window_hint_available",
        "source_date_start": source_date_start,
        "source_date_end": source_date_end,
        "receipt_path": str(resolved_receipt),
        "available_at": publication.get("available_at"),
    }


def _verify_formal_technical_reuse(
    plan: Mapping[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    """使用既有 custody verifier 重新驗證明確要求的 skip。"""

    if plan.get("status") != "ready":
        return {
            "status": "not_reused",
            "reason": str(plan.get("reason") or "formal_technical_plan_not_ready"),
        }
    from data_module.recommendation_calibration_source_contract import (
        reuse_verified_technical_computation_receipt,
    )

    reuse = reuse_verified_technical_computation_receipt(
        authorized_output_roots=[str(plan["formal_output_root"])],
        source_db=str(plan["source_db"]),
        source_date_start=str(plan["source_date_start"]),
        source_date_end=str(plan["source_date_end"]),
        availability_cutoff_at=now,
    )
    if reuse.get("status") != "reused":
        return {
            "status": "not_reused",
            "reason": str(
                reuse.get("reason") or "formal_technical_receipt_not_reusable"
            ),
            "reuse": dict(reuse),
        }
    source_publication_receipt = reuse.get("source_publication_receipt")
    if not isinstance(source_publication_receipt, Mapping) or not _same_path(
        source_publication_receipt.get("path"), Path(str(plan["receipt_path"]))
    ):
        return {
            "status": "not_reused",
            "reason": "formal_technical_receipt_pointer_not_reused",
            "reuse": dict(reuse),
        }
    return {"status": "reused", "reuse": dict(reuse)}


def _technical_child_invocation(
    *,
    data_root: Path,
    plan: Mapping[str, Any],
    base_environment: Mapping[str, str],
    window_weekdays: int,
    daily_delay_seconds: float,
    tpex_delay_seconds: float,
    broker_delay_seconds: float,
    calendar_cache_path: Path | None = None,
    temporary_closure_path: Path | None = None,
) -> tuple[list[str], dict[str, str]]:
    """組出 technical child command，同時保留其他 child 的 shadow routing。"""

    technical_output_root = Path(str(plan["formal_output_root"])).resolve()
    technical_environment = dict(base_environment)
    technical_environment.update(
        {
            "OUTPUT_ROOT": str(technical_output_root),
            "RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(technical_output_root),
            "DB_PATH": str(plan["source_db"]),
        }
    )
    arguments = [
        "--data-root",
        str(data_root),
        "--output-root",
        str(technical_output_root),
        "--formal-output-root",
        str(technical_output_root),
        "--start-date",
        str(plan["source_date_start"]),
        "--end-date",
        str(plan["source_date_end"]),
        "--window-weekdays",
        str(window_weekdays),
        "--daily-delay-seconds",
        str(daily_delay_seconds),
        "--tpex-delay-seconds",
        str(tpex_delay_seconds),
        "--broker-delay-seconds",
        str(broker_delay_seconds),
        "--status-path",
        str(plan["status_path"]),
        "--skip-broker-branch",
    ]
    if calendar_cache_path is not None:
        arguments.extend(["--calendar-cache-path", str(calendar_cache_path)])
    if temporary_closure_path is not None:
        arguments.extend(["--temporary-closure-path", str(temporary_closure_path)])
    return arguments, technical_environment


def _tail(text: str, limit: int = 6000) -> str:
    return text[-limit:] if len(text) > limit else text


def _snapshot_child_payload_from_stdout(
    raw_stdout: bytes,
) -> tuple[dict[str, Any] | None, str | None]:
    """從本次 snapshot child 的 stdout 取唯一、可驗證的 JSON 收據。"""

    try:
        stdout_text = raw_stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None, "snapshot_child_stdout_not_utf8"

    decoder = json.JSONDecoder()
    position = 0
    matches: list[dict[str, Any]] = []
    while position < len(stdout_text):
        start = stdout_text.find("{", position)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(stdout_text, start)
        except json.JSONDecodeError:
            position = start + 1
            continue
        position = end
        if (
            isinstance(value, dict)
            and value.get("task") == "baldr-recommendation-snapshot-daily"
        ):
            matches.append(value)

    if len(matches) != 1:
        return None, "snapshot_child_stdout_receipt_missing_or_ambiguous"

    payload = matches[0]
    if _iso_date(payload.get("decision_date")) is None:
        return None, "snapshot_child_stdout_decision_date_invalid"
    status = payload.get("status")
    if type(status) is not str or not status.strip():
        return None, "snapshot_child_stdout_status_missing"
    if status in {"passed", "passed_with_warnings", "warning", "degraded"}:
        result_id = payload.get("result_id")
        cohort = payload.get("snapshot_cohort")
        if type(result_id) is not str or not result_id.strip():
            return None, "snapshot_child_stdout_result_id_missing"
        if not isinstance(cohort, Mapping):
            return None, "snapshot_child_stdout_typed_cohort_missing"
        if cohort.get("schema_version") != "scheduled-recommendation-snapshot-cohort.v1":
            return None, "snapshot_child_stdout_cohort_schema_unsupported"
        if not _is_sha256_text(cohort.get("cohort_hash")):
            return None, "snapshot_child_stdout_cohort_hash_invalid"
        eligible_symbols = cohort.get("eligible_symbols")
        if (
            not isinstance(eligible_symbols, list)
            or not eligible_symbols
            or any(type(symbol) is not str or not symbol.strip() for symbol in eligible_symbols)
        ):
            return None, "snapshot_child_stdout_cohort_symbols_invalid"
    return payload, None


def _write_snapshot_invocation_stdout_artifact(
    *,
    path: Path,
    allowed_runs_root: Path,
    raw_stdout: bytes,
) -> tuple[str, int, str]:
    """將單次 child stdout 以限定路徑、大小與 create-only 語意保存。"""

    if type(raw_stdout) is not bytes:
        raise TypeError("snapshot child stdout 必須是原始 bytes")
    if len(raw_stdout) > _MAX_SNAPSHOT_INVOCATION_STDOUT_BYTES:
        raise ValueError("snapshot child stdout 超過 invocation artifact 大小上限")
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)

    def directory_identity(candidate: Path) -> tuple[int, int, int, int]:
        info = candidate.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & reparse_flag
        ):
            raise ValueError("snapshot stdout run/root component 必須是一般目錄")
        return (
            int(info.st_dev),
            int(info.st_ino),
            int(info.st_mode),
            int(getattr(info, "st_file_attributes", 0)),
        )

    def file_identity(candidate: Path) -> tuple[int, int, int, int, int, int, int]:
        info = candidate.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & reparse_flag
        ):
            raise ValueError("snapshot stdout artifact 必須是一般檔案")
        return (
            int(info.st_dev),
            int(info.st_ino),
            int(info.st_mode),
            int(info.st_size),
            int(info.st_mtime_ns),
            int(info.st_ctime_ns),
            int(getattr(info, "st_file_attributes", 0)),
        )

    try:
        canonical_runs_root = Path(allowed_runs_root).resolve(strict=True)
        canonical_parent = path.parent.resolve(strict=True)
        canonical_candidate = path.resolve(strict=False)
    except OSError as exc:
        raise ValueError("snapshot child stdout invocation root 無法驗證") from exc
    if (
        canonical_parent.parent != canonical_runs_root
        or path.name != _SNAPSHOT_INVOCATION_STDOUT_NAME
        or Path(os.path.abspath(path)) != canonical_candidate
    ):
        raise ValueError("snapshot child stdout artifact 超出本次 run root")

    try:
        root_before = directory_identity(canonical_runs_root)
        parent_before = directory_identity(canonical_parent)
        with path.open("xb") as stream:
            stream.write(raw_stdout)
            stream.flush()
            os.fsync(stream.fileno())
            opened = os.fstat(stream.fileno())
        file_before = file_identity(canonical_candidate)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino, opened.st_size)
            != (file_before[0], file_before[1], file_before[3])
            or file_before[3] != len(raw_stdout)
        ):
            raise ValueError("snapshot child stdout artifact write handle/path identity 不一致")
        readback = _read_regular_file_no_follow(
            canonical_candidate,
            canonical_runs_root,
            max_bytes=_MAX_SNAPSHOT_INVOCATION_STDOUT_BYTES,
        )
        file_after = file_identity(canonical_candidate)
        parent_after = directory_identity(canonical_parent)
        root_after = directory_identity(canonical_runs_root)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("snapshot child stdout artifact create-only write/readback 失敗") from exc
    if (
        readback != raw_stdout
        or file_after != file_before
        or parent_after != parent_before
        or root_after != root_before
    ):
        raise ValueError("snapshot child stdout artifact bytes 在 readback 時不一致")
    return (
        str(canonical_candidate),
        len(readback),
        "sha256:" + hashlib.sha256(readback).hexdigest(),
    )


def _run_child(
    *,
    name: str,
    script: str,
    arguments: Sequence[str],
    environment: Mapping[str, str],
    log_handle: Any,
    snapshot_stdout_artifact_path: Path | None = None,
    snapshot_stdout_runs_root: Path | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    command = [sys.executable, str(ROOT / script), *arguments]
    status_file = _status_path(Path(environment["RECOMMENDATION_LEARNING_OUTPUT_ROOT"]), name)
    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            env=dict(environment),
            capture_output=True,
            text=False,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        combined = (str(stdout) + str(stderr)).strip()
        log_handle.write(
            f"\n===== {name} TIMED OUT =====\n"
            f"timeout_seconds={timeout_seconds}\n{combined}\n"
        )
        return {
            "name": name,
            "script": script,
            "command": command,
            "returncode": None,
            "status": "timed_out",
            "status_path": str(status_file),
            "child_status": None,
            "child_warnings": [],
            "child_blockers": [f"subprocess_timeout:{name}"],
            "stdout_stderr_tail": _tail(combined),
            "timeout_seconds": timeout_seconds,
            "recoverable": True,
        }
    stdout_value = completed.stdout or b""
    stderr_value = completed.stderr or b""
    stdout_bytes = (
        stdout_value.encode("utf-8") if isinstance(stdout_value, str) else stdout_value
    )
    stderr_bytes = (
        stderr_value.encode("utf-8") if isinstance(stderr_value, str) else stderr_value
    )
    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    stderr_text = stderr_bytes.decode("utf-8", errors="replace")
    combined = (stdout_text + stderr_text).strip()
    log_handle.write(f"\n===== {name} =====\n{combined}\n")
    snapshot_receipt_error: str | None = None
    child_stdout_sha256: str | None = None
    child_stdout_artifact_path: str | None = None
    child_stdout_artifact_size: int | None = None
    child_status_source = "latest_status"
    if name == "recommendation_snapshot":
        child_status, snapshot_receipt_error = _snapshot_child_payload_from_stdout(
            stdout_bytes
        )
        if snapshot_stdout_artifact_path is None or snapshot_stdout_runs_root is None:
            snapshot_receipt_error = "snapshot_child_stdout_artifact_path_missing"
        else:
            try:
                (
                    child_stdout_artifact_path,
                    child_stdout_artifact_size,
                    child_stdout_sha256,
                ) = _write_snapshot_invocation_stdout_artifact(
                    path=snapshot_stdout_artifact_path,
                    allowed_runs_root=snapshot_stdout_runs_root,
                    raw_stdout=stdout_bytes,
                )
            except (OSError, TypeError, ValueError) as exc:
                snapshot_receipt_error = (
                    f"snapshot_child_stdout_artifact_invalid:{type(exc).__name__}"
                )
        child_status_source = "invocation_stdout_json"
    else:
        child_status = _read_json(status_file)
    child_status_name = (
        str(child_status.get("status") or "")
        if isinstance(child_status, Mapping)
        else ""
    )
    failed_child_statuses = {
        "failed",
        "blocked",
        "failed_training",
        "failed_dependency",
        "skipped_insufficient_evidence",
        "skipped_no_data",
        "error",
        "timed_out",
    }
    warning_child_statuses = {"passed_with_warnings", "warning", "degraded"}
    nested_blockers: list[str] = []
    nested_recoverable = False
    if name == "recommendation_learning" and isinstance(child_status, Mapping):
        live_capture = child_status.get("live_capture")
        if isinstance(live_capture, Mapping):
            capture_status = str(live_capture.get("status") or "").strip().lower()
            if capture_status in {"blocked", "failed"}:
                capture_reason = str(
                    live_capture.get("reason") or "capture_dependency_unavailable"
                ).strip()
                nested_blockers.append(
                    f"live_capture_{capture_status}:{capture_reason}"
                )
                nested_recoverable = (
                    capture_status == "blocked"
                    or child_status.get("cli_recoverable") is True
                )
    child_blockers = list(child_status.get("blockers") or []) if isinstance(child_status, Mapping) else []
    if snapshot_receipt_error is not None:
        child_blockers.append(snapshot_receipt_error)
    child_blockers.extend(nested_blockers)
    if (
        nested_blockers
        or snapshot_receipt_error is not None
        or completed.returncode != 0
        or child_status_name in failed_child_statuses
    ):
        step_status = "failed"
    elif child_status_name in warning_child_statuses:
        step_status = child_status_name
    elif child_status_name in {"passed", "published", "completed", "ready"}:
        step_status = "passed"
    elif not child_status_name:
        step_status = "failed"
    else:
        # Fail closed for a newly introduced child status.  The pipeline must
        # not report success while silently ignoring a child failure mode.
        step_status = "failed"
    return {
        "name": name,
        "script": script,
        "command": command,
        "returncode": completed.returncode,
        "status": step_status,
        "status_path": str(status_file),
        "child_status": child_status,
        "child_status_source": child_status_source,
        "child_stdout_artifact_path": child_stdout_artifact_path,
        "child_stdout_artifact_size": child_stdout_artifact_size,
        "child_stdout_sha256": child_stdout_sha256,
        "child_receipt_error": snapshot_receipt_error,
        "child_warnings": list(child_status.get("warnings") or [])
        if isinstance(child_status, Mapping)
        else [],
        "child_blockers": list(dict.fromkeys(str(item) for item in child_blockers)),
        "stdout_stderr_tail": _tail(combined),
        "timeout_seconds": timeout_seconds,
        "recoverable": nested_recoverable,
    }


def _base_payload(
    *,
    output_root: Path,
    status_path: Path,
    log_path: Path,
    decision_date: str,
    run_id: str,
    terminal_receipt_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": "daily-recommendation-learning-pipeline.v1",
        "task": TASK_NAME,
        "status": "running",
        "run_id": run_id,
        "decision_date": decision_date,
        "decision_timezone": "Asia/Taipei",
        "output_root": str(output_root),
        "status_path": str(status_path),
        "log_path": str(log_path),
        "terminal_receipt_path": str(terminal_receipt_path),
        "terminal_receipt_sha256": None,
        "failure_stage": None,
        "error_type": None,
        "error": None,
        "steps": {},
        "warnings": [],
        "blockers": [],
        "snapshot_warnings": [],
        "venue_date_source_gaps": [],
        "requested_symbols": [],
        "eligible_symbols": [],
        "missing_symbols": [],
        "degraded_symbols": [],
        "excluded_symbols": [],
        "moneydj_broker_branch": {
            "status": "skipped",
            "policy": "optional_source_outside_recommendation_learning_core_lane",
        },
        "formal_order_allowed": False,
        "shadow_only": True,
        "timeout_policy": {
            "child_timeout_is_recoverable": True,
            "durable_receipts_are_not_deleted_on_timeout": True,
        },
    }


def _snapshot_coverage(snapshot_status: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(snapshot_status, Mapping):
        return None
    value = snapshot_status.get("snapshot_cohort")
    return dict(value) if isinstance(value, Mapping) else None


def _apply_coverage(payload: dict[str, Any], coverage: Mapping[str, Any] | None) -> None:
    if not isinstance(coverage, Mapping):
        return
    payload["snapshot_cohort"] = dict(coverage)
    payload["requested_symbols"] = list(coverage.get("requested_symbols") or [])
    payload["eligible_symbols"] = list(coverage.get("eligible_symbols") or [])
    payload["missing_symbols"] = list(coverage.get("missing_symbols") or [])
    payload["degraded_symbols"] = list(coverage.get("degraded_symbols") or [])
    payload["excluded_symbols"] = list(coverage.get("excluded_symbols") or [])


def _is_sha256_text(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(char in "0123456789abcdef" for char in value[7:])
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.child_timeout_seconds <= 0 or args.pipeline_timeout_seconds <= 0:
        raise ValueError("timeout budgets must be positive")
    data_root = args.data_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    source_db = (args.source_db or data_root / "sqlite" / "twstock.db").expanduser().resolve()
    decision_date = datetime.now(TAIPEI).date().isoformat()
    run_root = output_root / "scheduled" / "recommendation_calibration_learning"
    status_path = run_root / "latest_status.json"
    log_path = run_root / f"{decision_date.replace('-', '')}_pipeline.log"
    run_id = (
        f"{decision_date.replace('-', '')}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-"
        f"{uuid4().hex[:12]}"
    )
    terminal_receipt_path = run_root / "runs" / run_id / "receipt.json"
    run_root.mkdir(parents=True, exist_ok=True)
    snapshot_stdout_runs_root = run_root / "runs"
    snapshot_stdout_runs_root.mkdir(parents=True, exist_ok=True)
    invocation_dir = terminal_receipt_path.parent
    invocation_dir.mkdir(parents=True, exist_ok=False)
    snapshot_stdout_artifact_path = (
        invocation_dir / _SNAPSHOT_INVOCATION_STDOUT_NAME
    )

    environment = os.environ.copy()
    environment.update(
        {
            "OUTPUT_ROOT": str(output_root),
            "RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(output_root),
            "DB_PATH": str(source_db),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    payload = _base_payload(
        output_root=output_root,
        status_path=status_path,
        log_path=log_path,
        decision_date=decision_date,
        run_id=run_id,
        terminal_receipt_path=terminal_receipt_path,
    )
    _write_json(status_path, payload)

    pipeline_deadline = time.monotonic() + args.pipeline_timeout_seconds

    def run_child_bounded(**kwargs: Any) -> dict[str, Any]:
        remaining = pipeline_deadline - time.monotonic()
        if remaining <= 0:
            name = str(kwargs["name"])
            script = str(kwargs["script"])
            child_environment = kwargs.get("environment") or environment
            child_output_root = Path(
                child_environment["RECOMMENDATION_LEARNING_OUTPUT_ROOT"]
            )
            status_file = _status_path(child_output_root, name)
            log_handle = kwargs["log_handle"]
            log_handle.write(
                f"\n===== {name} TIMED OUT =====\n"
                "pipeline_timeout_seconds_exhausted\n"
            )
            return {
                "name": name,
                "script": script,
                "command": [sys.executable, str(ROOT / script), *kwargs["arguments"]],
                "returncode": None,
                "status": "timed_out",
                "status_path": str(status_file),
                "child_status": None,
                "child_warnings": [],
                "child_blockers": [f"pipeline_timeout:{name}"],
                "stdout_stderr_tail": "",
                "timeout_seconds": 0.0,
                "recoverable": True,
            }
        timeout_seconds = min(args.child_timeout_seconds, remaining)
        return _run_child(timeout_seconds=timeout_seconds, **kwargs)

    stage = "pipeline_start"
    try:
        with log_path.open("a", encoding="utf-8") as log_handle:
            technical_now = datetime.now(TAIPEI)
            if args.skip_technical_refresh:
                stage = "technical_window_hint"
                technical_plan = _formal_receipt_window_hint(
                    data_root=data_root,
                    source_db=source_db,
                )
                if _technical_window_matches_decision(
                    technical_plan,
                    decision_date=decision_date,
                    now=technical_now,
                ):
                    stage = "technical_reuse"
                    reuse = _verify_formal_technical_reuse(
                        technical_plan,
                        now=technical_now,
                    )
                else:
                    reuse = {
                        "status": "not_reused",
                        "reason": str(
                            technical_plan.get("reason")
                            if technical_plan.get("status") != "ready"
                            else "formal_technical_receipt_not_same_day"
                        ),
                    }
                if reuse.get("status") == "reused":
                    reuse_payload = reuse.get("reuse")
                    technical_step = {
                        "name": "data_update_quick",
                        "status": "skipped",
                        "reason": "caller_declared_existing_same_day_technical_receipt",
                        "source": "formal_data_root",
                        "formal_output_root": technical_plan.get("formal_output_root"),
                        "receipt_path": technical_plan.get("receipt_path"),
                        "source_date_start": technical_plan.get("source_date_start"),
                        "source_date_end": technical_plan.get("source_date_end"),
                        "status_path": technical_plan.get("status_path"),
                        "technical_reuse_validation": reuse_payload,
                    }
                else:
                    technical_step = {
                        "name": "data_update_quick",
                        "status": "blocked",
                        "reason": str(
                            reuse.get("reason")
                            or technical_plan.get("reason")
                            or "formal_technical_receipt_not_reusable"
                        ),
                        "source": "formal_data_root",
                        "formal_output_root": technical_plan.get("formal_output_root"),
                        "receipt_path": technical_plan.get("receipt_path"),
                        "source_date_start": technical_plan.get("source_date_start"),
                        "source_date_end": technical_plan.get("source_date_end"),
                        "status_path": technical_plan.get("status_path"),
                        "technical_reuse_validation": reuse,
                    }
            else:
                stage = "technical_plan"
                technical_plan = _technical_child_plan(
                    data_root=data_root,
                    source_db=source_db,
                    source_date_start=decision_date,
                    source_date_end=decision_date,
                )
                if technical_plan.get("status") == "ready":
                    stage = "technical_window_hint"
                    window_hint = _formal_receipt_window_hint(
                        data_root=data_root,
                        source_db=source_db,
                    )
                    if _technical_window_matches_decision(
                        window_hint,
                        decision_date=decision_date,
                        now=technical_now,
                    ):
                        hinted_plan = _technical_child_plan(
                            data_root=data_root,
                            source_db=source_db,
                            source_date_start=str(window_hint["source_date_start"]),
                            source_date_end=str(window_hint["source_date_end"]),
                        )
                        hinted_plan.update(
                            {
                                "receipt_path": window_hint.get("receipt_path"),
                                "available_at": window_hint.get("available_at"),
                            }
                        )
                        stage = "technical_reuse"
                        reuse = _verify_formal_technical_reuse(
                            hinted_plan,
                            now=technical_now,
                        )
                        if reuse.get("status") == "reused":
                            technical_plan = hinted_plan
                            technical_plan["window_hint"] = (
                                "formal_latest_technical_publication_verified_reuse"
                            )
                if technical_plan.get("status") != "ready":
                    technical_step = {
                        "name": "data_update_quick",
                        "status": "blocked",
                        "reason": str(
                            technical_plan.get("reason")
                            or "canonical_formal_technical_child_unavailable"
                        ),
                        "source": "formal_data_root",
                        "formal_output_root": technical_plan.get("formal_output_root"),
                        "source_date_start": technical_plan.get("source_date_start"),
                        "source_date_end": technical_plan.get("source_date_end"),
                        "status_path": technical_plan.get("status_path"),
                    }
                else:
                    technical_arguments, technical_environment = _technical_child_invocation(
                        data_root=data_root,
                        plan=technical_plan,
                        base_environment=environment,
                        window_weekdays=args.window_weekdays,
                        daily_delay_seconds=args.daily_delay_seconds,
                        tpex_delay_seconds=args.tpex_delay_seconds,
                        broker_delay_seconds=args.broker_delay_seconds,
                        calendar_cache_path=args.calendar_cache_path,
                        temporary_closure_path=args.temporary_closure_path,
                    )
                    stage = "technical_child"
                    technical_step = run_child_bounded(
                        name="data_update_quick",
                        script="scripts/scheduled/run_daily_data_update_quick.py",
                        arguments=technical_arguments,
                        environment=technical_environment,
                        log_handle=log_handle,
                    )
                    technical_step.update(
                        {
                            "source": "formal_data_root",
                            "formal_output_root": technical_plan.get("formal_output_root"),
                            "receipt_path": technical_plan.get("receipt_path"),
                            "source_date_start": technical_plan.get("source_date_start"),
                            "source_date_end": technical_plan.get("source_date_end"),
                            "window_hint": technical_plan.get("window_hint")
                            or "caller_decision_date_fallback",
                        }
                    )
            payload["steps"]["data_update_quick"] = technical_step
            if technical_step.get("status") in {"failed", "blocked", "timed_out"}:
                payload["warnings"].append("technical_source_refresh_failed_or_partial")
            if technical_step.get("status") == "failed":
                payload["blockers"].append("technical_source_refresh_failed")
            if technical_step.get("status") == "blocked":
                payload["blockers"].append("technical_source_refresh_blocked")
            if technical_step.get("status") == "timed_out":
                payload["blockers"].append("technical_source_refresh_timed_out")
            technical_warnings = list(technical_step.get("child_warnings") or [])
            payload["warnings"].extend(technical_warnings)
            payload["venue_date_source_gaps"] = [
                warning
                for warning in technical_warnings
                if "TPEX" in str(warning).upper() or "TPEx" in str(warning)
            ]

            stage = "official_market_events"
            official_step = run_child_bounded(
                name="official_market_events",
                script="scripts/scheduled/run_official_market_event_backfill.py",
                arguments=[
                    "--output-root", str(output_root),
                    "--as-of-date", decision_date,
                    "--publication-scope", "prospective_bounded",
                    "--start-year", decision_date[:4],
                    "--end-year", decision_date[:4],
                    "--timeout-seconds", str(args.official_timeout_seconds),
                    "--max-attempts", str(args.official_max_attempts),
                    "--retry-delay-seconds", str(args.official_retry_delay_seconds),
                    "--request-delay-seconds", str(args.official_request_delay_seconds),
                ],
                environment=environment,
                log_handle=log_handle,
            )
            payload["steps"]["official_market_events"] = official_step
            official_status = _read_json(_status_path(output_root, "official_market_events"))
            last_good = official_status.get("last_known_good_publication") if isinstance(official_status, Mapping) else None
            if official_step.get("status") == "timed_out":
                payload["blockers"].append("official_refresh_timed_out")
            elif official_step.get("status") == "failed":
                if isinstance(last_good, Mapping) and last_good.get("validation_status") == "verified":
                    payload["warnings"].append("official_refresh_failed_verified_last_good_preserved")
                else:
                    payload["blockers"].append("official_refresh_failed_without_verified_last_good")

            stage = "recommendation_snapshot"
            snapshot_step = run_child_bounded(
                name="recommendation_snapshot",
                script="scripts/scheduled/run_scheduled_recommendation_snapshot.py",
                arguments=[
                    "--data-root", str(data_root),
                    "--output-root", str(output_root),
                    "--max-stocks", str(args.max_stocks),
                    "--top-n", str(args.top_n),
                ],
                environment=environment,
                log_handle=log_handle,
                snapshot_stdout_artifact_path=snapshot_stdout_artifact_path,
                snapshot_stdout_runs_root=snapshot_stdout_runs_root,
            )
            payload["steps"]["recommendation_snapshot"] = snapshot_step
            # 僅使用這次 child invocation 回傳的 status；不從可被另一個
            # 同日排程覆寫的 latest_status.json 重新挑選 snapshot identity。
            snapshot_status = snapshot_step.get("child_status")
            snapshot_status = snapshot_status if isinstance(snapshot_status, Mapping) else None
            coverage = _snapshot_coverage(snapshot_status)
            _apply_coverage(payload, coverage)
            snapshot_warnings = list(snapshot_status.get("warnings") or []) if isinstance(snapshot_status, Mapping) else []
            payload["snapshot_warnings"] = snapshot_warnings
            payload["warnings"].extend(snapshot_warnings)
            if coverage and coverage.get("missing_symbols"):
                payload["warnings"].append("recommendation_snapshot_missing_symbols")
            acceptable_snapshot_statuses = {"passed", "passed_with_warnings", "warning", "degraded"}
            snapshot_result_id = (
                snapshot_status.get("result_id")
                if isinstance(snapshot_status, Mapping)
                else None
            )
            snapshot_cohort_hash = (
                coverage.get("cohort_hash")
                if isinstance(coverage, Mapping)
                else None
            )
            snapshot_invocation_output_sha256 = snapshot_step.get(
                "child_stdout_sha256"
            )
            snapshot_invocation_output_path = snapshot_step.get(
                "child_stdout_artifact_path"
            )
            snapshot_binding_ready = (
                type(snapshot_result_id) is str
                and bool(snapshot_result_id.strip())
                and _is_sha256_text(snapshot_cohort_hash)
                and _is_sha256_text(snapshot_invocation_output_sha256)
                and type(snapshot_invocation_output_path) is str
                and bool(snapshot_invocation_output_path.strip())
                and (
                    snapshot_status.get("decision_date") == decision_date
                    if isinstance(snapshot_status, Mapping)
                    else False
                )
            )
            if (
                snapshot_step.get("status") not in acceptable_snapshot_statuses
                or not isinstance(snapshot_status, Mapping)
                or snapshot_status.get("status") not in acceptable_snapshot_statuses
                or (not args.symbols and not snapshot_binding_ready)
            ):
                payload["blockers"].append("same_day_recommendation_snapshot_unavailable")
                payload["steps"]["recommendation_learning"] = {
                    "status": "blocked",
                    "reason": "same_day_recommendation_snapshot_unavailable",
                }
            else:
                learning_arguments = [
                    "--data-root", str(data_root),
                    "--output-root", str(output_root),
                    "--source-db", str(source_db),
                    "--history-start-date", str(args.history_start_date),
                    "--fixed-round-trip-cost-bp", str(args.fixed_round_trip_cost_bp),
                    "--max-decision-dates", str(args.max_decision_dates),
                    "--replay-selection-policy", "latest_eligible_dates",
                    "--decision-date", decision_date,
                    "--training-as-of", decision_date,
                ]
                if args.cost_scenario == "banktaiwan_estimated_research":
                    learning_arguments.extend(
                        [
                            "--cost-scenario", args.cost_scenario,
                            "--cost-policy-estimate-date", str(args.cost_policy_estimate_date),
                            "--research-order-lot-type", str(args.research_order_lot_type),
                            "--research-instrument-type", str(args.research_instrument_type),
                        ]
                    )
                    if args.research_order_amount_twd is not None:
                        learning_arguments.extend(
                            ["--research-order-amount-twd", str(args.research_order_amount_twd)]
                        )
                    if args.research_order_quantity_shares is not None:
                        learning_arguments.extend(
                            [
                                "--research-order-quantity-shares",
                                str(args.research_order_quantity_shares),
                            ]
                        )
                if args.symbols:
                    learning_arguments.extend(["--symbols", str(args.symbols)])
                else:
                    learning_arguments.extend(
                        [
                            "--snapshot-output-root", str(output_root),
                            "--snapshot-result-id", str(snapshot_result_id),
                            "--snapshot-cohort-hash", str(snapshot_cohort_hash),
                            "--snapshot-invocation-output-sha256",
                            str(snapshot_invocation_output_sha256),
                            "--snapshot-invocation-output-path",
                            str(snapshot_invocation_output_path),
                        ]
                    )
                stage = "recommendation_learning"
                learning_step = run_child_bounded(
                    name="recommendation_learning",
                    script="scripts/scheduled/run_daily_recommendation_learning.py",
                    arguments=learning_arguments,
                    environment=environment,
                    log_handle=log_handle,
                )
                payload["steps"]["recommendation_learning"] = learning_step
                payload["warnings"].extend(list(learning_step.get("child_warnings") or []))
                payload["blockers"].extend(list(learning_step.get("child_blockers") or []))
                learning_status = _read_json(output_root / "recommendation_learning" / "latest_status.json")
                if isinstance(learning_status, Mapping):
                    payload["learning_latest_status"] = {
                        "status": learning_status.get("status"),
                        "decision": learning_status.get("decision"),
                        "decision_reason": learning_status.get("decision_reason"),
                        "symbol_source": learning_status.get("symbol_source"),
                        "symbols": learning_status.get("symbols"),
                        "symbol_coverage": learning_status.get("symbol_coverage"),
                        "run_scope": learning_status.get("run_scope"),
                        "live_capture": learning_status.get("live_capture"),
                    }
                if learning_step.get("status") not in {"passed", "passed_with_warnings"}:
                    payload["blockers"].append("recommendation_learning_failed")

    except Exception as exc:
        payload["blockers"].append(f"pipeline_exception:{type(exc).__name__}")
        payload["error_type"] = type(exc).__name__
        payload["error"] = str(exc)[:1000]
        payload["failure_stage"] = stage

    payload["warnings"] = list(dict.fromkeys(str(item) for item in payload["warnings"]))
    payload["blockers"] = list(dict.fromkeys(str(item) for item in payload["blockers"]))
    learning_step = payload["steps"].get("recommendation_learning")
    if not payload["blockers"] and isinstance(learning_step, Mapping) and learning_step.get("status") in {"passed", "passed_with_warnings"}:
        payload["status"] = "passed_with_warnings" if payload["warnings"] else "passed"
    else:
        payload["status"] = "failed"
    payload["completed_at"] = datetime.now(TAIPEI).isoformat(timespec="seconds")
    try:
        payload["terminal_receipt_sha256"] = _write_terminal_receipt(
            terminal_receipt_path,
            _terminal_receipt_projection(payload),
        )
    except Exception as exc:
        payload["status"] = "failed"
        payload["blockers"].append("terminal_receipt_write_failed")
        payload["terminal_receipt_error_type"] = type(exc).__name__
        payload["terminal_receipt_error"] = str(exc)[:1000]
        if not payload.get("error_type"):
            payload["error_type"] = type(exc).__name__
            payload["error"] = str(exc)[:1000]
            payload["failure_stage"] = "terminal_receipt"
    payload["warnings"] = list(dict.fromkeys(str(item) for item in payload["warnings"]))
    payload["blockers"] = list(dict.fromkeys(str(item) for item in payload["blockers"]))
    _write_json(status_path, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] in {"passed", "passed_with_warnings"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
