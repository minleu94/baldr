"""同一自然日內執行 Paper EOD 的有界重試 orchestration。

這是 scheduler 邊界，會先執行唯讀 dependency gate，再呼叫既有
``run_isolated`` adapter。只有明確的行情尚未到齊／上游收據尚未完成狀態才
等待並重試；identity、scope、schema 或其他 terminal blocker 會立即停止。
所有等待使用 Python ``time.sleep``，適用於沒有互動 stdin 的 Task Scheduler。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence
import uuid
from zoneinfo import ZoneInfo

# Task Scheduler invokes this file by path, so Python's import root is the
# sibling ``scripts/scheduled`` directory rather than the repository root.
# Insert the repository root before importing the existing adapter; this has no
# filesystem side effect and keeps the wrapper runnable outside an IDE.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.scheduled.paper_execution_dependency_gate import inspect_dependency
from scripts.scheduled.daily_operations_receipt import code_version, write_terminal_receipt
from scripts.scheduled.run_paper_execution_daily_isolated import run_isolated


TAIPEI = ZoneInfo("Asia/Taipei")
DEFAULT_GATE_OUTPUT_ROOT = REPO_ROOT / "output" / "paper_execution_eod_replay" / "dependency_gate"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 900

_RETRYABLE_GATE_MARKERS = (
    "quick_update_receipt_data_date_not_target",
    "quick_update_receipt_checked_date_not_target",
    "quick_update_twse_step_not_passed",
    "quick_update_sqlite_sync_step_not_passed",
    "freshness_receipt_daily_prices_not_target",
    "freshness_receipt_update_date_not_target",
    "daily_prices_target_open_rows_unavailable",
    "source_file_missing:",
    "source_file_set_incomplete",
)
_TRANSIENT_RECEIPT_STATES = frozenset(
    {"running", "pending", "in_progress", "waiting", "not_run", "missing", "unknown"}
)
_RETRYABLE_ADAPTER_MARKERS = (
    "daily_prices is missing execution-date open rows:",
    "paper_execution_waiting_for_delayed_eod_source:",
    "paper_execution_waiting_for_next_session_open:",
    "execution_source:",
)
_NO_OP_GATE_STATUSES = frozenset({"official_no_data", "not_trading_day"})


def _roll_forward_if_configured() -> dict[str, object] | None:
    """在既有 Paper EOD scheduler 邊界觸發下一自然日 candidate producer。

    Scheduler 只需把兩個 immutable source pins 傳入 process；缺少 pin 時
    保留既有 Paper retry 行為，讓 root／Ops 能先做環境 preflight。這個
    hook 永遠只建立 candidate config，不能套用 controlled path 或產生
    fill。
    """

    from data_module.formal_runtime_roll_forward import (
        CALENDAR_BUNDLE_ENV,
        PORTFOLIO_CLOCK_ENV,
        run_from_environment,
    )
    from data_module.formal_runtime_config import (
        FORMAL_RUNTIME_CONFIG_ENV,
        RUNTIME_CONFIG_ROOT_ENV,
        load_runtime_environment_binding,
    )

    try:
        load_runtime_environment_binding()
    except Exception as error:  # noqa: BLE001 - observable scheduler boundary
        return {
            "status": "runtime_roll_forward_failed",
            "exit_code": 2,
            "blockers": [
                f"runtime_environment_binding_invalid:{type(error).__name__}:{str(error).splitlines()[0][:220]}"
            ],
            "candidate_only": True,
            "formal_oos_allowed": False,
        }
    runtime_is_configured = bool(
        os.environ.get(FORMAL_RUNTIME_CONFIG_ENV, "").strip()
        or os.environ.get(RUNTIME_CONFIG_ROOT_ENV, "").strip()
        or os.environ.get(CALENDAR_BUNDLE_ENV, "").strip()
        or os.environ.get(PORTFOLIO_CLOCK_ENV, "").strip()
    )
    if not runtime_is_configured:
        return None
    missing_pins = [
        name
        for name in (CALENDAR_BUNDLE_ENV, PORTFOLIO_CLOCK_ENV)
        if not os.environ.get(name, "").strip()
    ]
    if missing_pins:
        return {
            "status": "runtime_roll_forward_not_configured",
            "exit_code": 2,
            "blockers": [
                "runtime_roll_forward_required_source_pins_missing:"
                + ",".join(missing_pins)
            ],
            "candidate_only": True,
            "formal_oos_allowed": False,
        }
    try:
        status, exit_code = run_from_environment(emit=False)
    except Exception as error:  # noqa: BLE001 - observable scheduler boundary
        return {
            "status": "runtime_roll_forward_failed",
            "exit_code": 2,
            "blockers": [
                f"runtime_roll_forward_exception:{type(error).__name__}:{str(error).splitlines()[0][:220]}"
            ],
            "candidate_only": True,
            "formal_oos_allowed": False,
        }
    result: dict[str, object] = {
        "status": status.get("status"),
        "exit_code": exit_code,
        "activation_trading_day": status.get("activation_trading_day"),
        "runtime_config_path": status.get("runtime_config_path"),
        "runtime_config_file_hash": status.get("runtime_config_file_hash"),
        "status_path": status.get("status_path"),
        "blockers": _object_list(status.get("blockers")),
        "candidate_only": status.get("candidate_only") is True,
        "formal_oos_allowed": status.get("formal_oos_allowed") is True,
    }
    return result


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    """在同一目錄以 replace 原子切換 latest pointer，避免半檔被讀到。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = stream.name
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass


def _write_gate_receipt(
    payload: Mapping[str, object],
    *,
    output_root: Path,
    attempt: int,
    observed: datetime,
) -> dict[str, object]:
    """保存唯一 gate receipt，並以可覆寫 latest pointer 指向最新檔案。"""

    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    encoded = _canonical_json({**dict(payload), "attempt": attempt}) + b"\n"
    stamp = observed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    receipt_path: Path | None = None
    for suffix in range(100):
        suffix_text = "" if suffix == 0 else f"_{suffix}"
        candidate = output_root / f"dependency_gate_{stamp}_attempt{attempt}{suffix_text}.json"
        try:
            with candidate.open("xb") as stream:
                stream.write(encoded)
                stream.flush()
            receipt_path = candidate
            break
        except FileExistsError:
            continue
    if receipt_path is None:
        raise RuntimeError("paper dependency gate receipt filename exhausted")
    file_hash = "sha256:" + hashlib.sha256(encoded).hexdigest()
    latest = {
        "schema_version": "paper-execution-dependency-gate-latest.v1",
        "updated_at": observed.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "latest_path": str(receipt_path),
        "latest_file_sha256": file_hash,
        "attempt": attempt,
        "query_only": True,
        "source_db_written": False,
        "source_files_written": False,
    }
    latest_path = output_root / "latest.json"
    _atomic_write_json(latest_path, latest)
    return {
        "path": str(receipt_path),
        "file_sha256": file_hash,
        "latest_pointer": str(latest_path),
    }


def _marker_matches(text: str, marker: str) -> bool:
    """Match an explicit blocker code or a declared ``prefix:`` code."""

    if marker.endswith(":"):
        return text == marker[:-1] or text.startswith(marker)
    return text == marker


def _all_markers_match(values: object, markers: Sequence[str]) -> bool:
    """只有每一個 blocker 都是明確暫時狀態時才允許重試。"""

    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return False
    values_list = list(values)
    return bool(values_list) and all(
        any(_marker_matches(str(value).strip().lower(), marker) for marker in markers)
        for value in values_list
    )


def _gate_blocker_is_retryable(value: object) -> bool:
    text = str(value).strip().lower()
    for prefix in (
        "quick_update_receipt_unavailable:",
        "freshness_receipt_unavailable:",
    ):
        if text.startswith(prefix):
            # A missing latest receipt may simply mean the upstream task has
            # not completed yet. Malformed, permission, or other read errors
            # are terminal and must be investigated instead of retried.
            return text[len(prefix) :].startswith("missing:")
    for prefix in (
        "quick_update_status_not_success:",
        "freshness_status_not_passed:",
    ):
        if text.startswith(prefix):
            return text[len(prefix) :] in _TRANSIENT_RECEIPT_STATES
    return any(_marker_matches(text, marker) for marker in _RETRYABLE_GATE_MARKERS)


def _gate_retryable(gate: Mapping[str, object]) -> bool:
    blockers = gate.get("blockers")
    if not isinstance(blockers, Sequence) or isinstance(blockers, (str, bytes)):
        return False
    values = list(blockers)
    return bool(values) and all(_gate_blocker_is_retryable(value) for value in values)


def _object_list(value: object) -> list[object]:
    """Narrow an untrusted JSON value before iterating or copying it."""

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _adapter_retryable(result: Mapping[str, object]) -> bool:
    blockers = result.get("blockers")
    nested = result.get("result")
    nested_blockers = nested.get("blockers") if isinstance(nested, Mapping) else None
    values = _object_list(blockers)
    values.extend(_object_list(nested_blockers))
    return _all_markers_match(values, _RETRYABLE_ADAPTER_MARKERS)


def run_scheduled(
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_delay_seconds: int = DEFAULT_RETRY_DELAY_SECONDS,
    gate_output_root: str | Path = DEFAULT_GATE_OUTPUT_ROOT,
    gate_fn: Callable[[], Mapping[str, object]] | None = None,
    adapter_fn: Callable[[], Mapping[str, object]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    now_fn: Callable[[], datetime] | None = None,
    roll_forward_fn: Callable[[], Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """執行有界、同一台北自然日、同一 frozen recommendation 的 retry。"""

    if max_attempts < 1 or max_attempts > 5:
        raise ValueError("max_attempts must be between 1 and 5")
    if retry_delay_seconds < 0 or retry_delay_seconds > 3600:
        raise ValueError("retry_delay_seconds must be between 0 and 3600")

    gate_reader = gate_fn or (lambda: inspect_dependency())
    adapter_runner = adapter_fn or run_isolated
    clock = now_fn or (lambda: datetime.now(timezone.utc))
    first_date = clock().astimezone(TAIPEI).date()
    records: list[dict[str, object]] = []
    last_result: Mapping[str, object] = {
        "status": "blocked",
        "blockers": ["paper_execution_retry_not_started"],
    }

    for attempt in range(1, max_attempts + 1):
        observed = clock().astimezone(timezone.utc)
        current_date = observed.astimezone(TAIPEI).date()
        if current_date != first_date:
            terminal = {
                "status": "blocked",
                "blockers": ["paper_execution_natural_day_changed_before_retry"],
            }
            records.append({"attempt": attempt, "terminal": True, "reason": terminal["blockers"][0]})
            last_result = terminal
            break

        gate = dict(gate_reader())
        gate_receipt = _write_gate_receipt(
            gate,
            output_root=Path(gate_output_root),
            attempt=attempt,
            observed=observed,
        )
        record: dict[str, object] = {
            "attempt": attempt,
            "gate_status": gate.get("status"),
            "gate_ready": bool(gate.get("ready")),
            "gate_target_date": gate.get("target_date"),
            "gate_blocker_count": len(_object_list(gate.get("blockers"))),
            "gate_receipt": gate_receipt,
        }

        if not bool(gate.get("ready")):
            record["gate_blockers"] = _object_list(gate.get("blockers"))
            if not _gate_retryable(gate) or attempt >= max_attempts:
                record["terminal"] = True
                records.append(record)
                last_result = {
                    "status": "blocked",
                    "blockers": record["gate_blockers"],
                    "dependency_gate": gate_receipt,
                }
                break
            record["retry_reason"] = "dependency_gate_transient"
            records.append(record)
            sleep_fn(retry_delay_seconds)
            continue

        gate_status = str(gate.get("status"))
        if gate_status in _NO_OP_GATE_STATUSES:
            # Both the official updater and the weekend fast path are explicit
            # calendar no-ops.  Neither may enter the fill-producing adapter;
            # the post-loop runtime roll-forward still runs so the next
            # official date config can be prepared from the same source pins.
            record["terminal"] = True
            record["retry_reason"] = (
                "official_no_data_noop"
                if gate_status == "official_no_data"
                else "not_trading_day_noop"
            )
            records.append(record)
            last_result = {
                "status": "skipped_non_trading_day",
                "blockers": _object_list(gate.get("blockers")),
                "dependency_gate": gate_receipt,
                "official_no_data": gate_status == "official_no_data",
                "non_trading_day": gate_status == "not_trading_day",
                "adapter_called": False,
            }
            break

        result = dict(adapter_runner())
        last_result = result
        record["adapter_status"] = result.get("status")
        if str(result.get("status")) in {
            "machine_verified_candidate",
            "no_trade_required_candidate",
            "skipped_non_trading_day",
            "skipped_no_pending_recommendation",
            "waiting_for_execution_session",
            "waiting_for_execution_source",
        }:
            record["terminal"] = True
            records.append(record)
            break
        if not _adapter_retryable(result) or attempt >= max_attempts:
            record["terminal"] = True
            records.append(record)
            break
        record["retry_reason"] = "adapter_transient_source_blocker"
        records.append(record)
        sleep_fn(retry_delay_seconds)

    final = dict(last_result)
    final["scheduled_retry"] = {
        "schema_version": "paper-execution-scheduled-retry.v1",
        "max_attempts": max_attempts,
        "retry_delay_seconds": retry_delay_seconds,
        "same_taipei_natural_day_required": True,
        "same_frozen_recommendation_required": True,
        "attempts": records,
    }
    roll_forward_runner = roll_forward_fn or _roll_forward_if_configured
    roll_forward = roll_forward_runner()
    if roll_forward is not None:
        final["runtime_roll_forward"] = dict(roll_forward)
        roll_status = str(roll_forward.get("status"))
        roll_exit_code = roll_forward.get("exit_code")
        roll_succeeded = roll_status in {
            "runtime_config_created",
            "runtime_config_reused",
        } and roll_exit_code == 0
        if not roll_succeeded:
            paper_status = final.get("status")
            final["paper_execution_status"] = paper_status
            final["status"] = "degraded_runtime_roll_forward"
            final["exit_code"] = 2
            final["blockers"] = [
                "runtime_roll_forward_not_ready:" + roll_status,
                *_object_list(roll_forward.get("blockers")),
            ]
    return final


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--retry-delay-seconds", type=int, default=DEFAULT_RETRY_DELAY_SECONDS)
    parser.add_argument("--gate-output-root", type=Path, default=DEFAULT_GATE_OUTPUT_ROOT)
    return parser


_PAPER_TERMINAL_SUCCESS_STATUSES = frozenset(
    {
        "machine_verified_candidate",
        "no_trade_required_candidate",
        "skipped_non_trading_day",
        "skipped_no_pending_recommendation",
        "waiting_for_execution_session",
        "waiting_for_execution_source",
    }
)


def _paper_terminal_exit_code(result: Mapping[str, object]) -> int:
    return 0 if str(result.get("status")) in _PAPER_TERMINAL_SUCCESS_STATUSES else 2


def _terminal_gate_attempts(result: Mapping[str, object]) -> list[dict[str, object]]:
    retry = result.get("scheduled_retry")
    attempts = retry.get("attempts") if isinstance(retry, Mapping) else None
    if retry is None and attempts is None:
        if "scheduled_retry" in result:
            raise ValueError("paper_terminal_retry_result_invalid")
        return []
    if not isinstance(attempts, Sequence) or isinstance(attempts, (str, bytes)):
        raise ValueError("paper_terminal_gate_attempts_invalid")
    if len(attempts) > 5:
        raise ValueError("paper_terminal_gate_attempts_exceed_bound")
    summaries: list[dict[str, object]] = []
    for expected_attempt, record in enumerate(attempts, start=1):
        if not isinstance(record, Mapping):
            raise ValueError("paper_terminal_gate_attempt_invalid")
        attempt = record.get("attempt")
        if type(attempt) is not int or attempt != expected_attempt or attempt > 5:
            raise ValueError("paper_terminal_gate_attempt_number_invalid")
        receipt = record.get("gate_receipt")
        receipt_ref: dict[str, str] | None = None
        cross_day_terminal = (
            record.get("terminal") is True
            and record.get("reason") == "paper_execution_natural_day_changed_before_retry"
            and "gate_status" not in record
            and "gate_ready" not in record
            and receipt is None
        )
        if cross_day_terminal:
            if set(record) != {"attempt", "terminal", "reason"}:
                raise ValueError("paper_terminal_cross_day_record_invalid")
        elif not set(record).issubset(
            {
                "attempt",
                "gate_status",
                "gate_ready",
                "gate_target_date",
                "gate_blocker_count",
                "gate_receipt",
                "gate_blockers",
                "terminal",
                "retry_reason",
                "adapter_status",
            }
        ):
            raise ValueError("paper_terminal_gate_attempt_unknown_fields")
        if "terminal" in record and type(record["terminal"]) is not bool:
            raise ValueError("paper_terminal_gate_terminal_flag_invalid")
        for text_field in ("retry_reason", "adapter_status"):
            value = record.get(text_field)
            if value is not None and (not isinstance(value, str) or not value or len(value) > 128):
                raise ValueError("paper_terminal_gate_attempt_text_invalid")
        raw_blockers = record.get("gate_blockers")
        if raw_blockers is not None:
            if not isinstance(raw_blockers, list):
                raise ValueError("paper_terminal_gate_blocker_count_invalid")
            if len(raw_blockers) != record.get("gate_blocker_count"):
                raise ValueError("paper_terminal_gate_blocker_count_mismatch")
        if isinstance(receipt, Mapping):
            path = receipt.get("path")
            digest = receipt.get("file_sha256")
            if (
                isinstance(path, str)
                and path
                and len(path) <= 2048
                and isinstance(digest, str)
                and digest.startswith("sha256:")
                and len(digest) == 71
                and all(character in "0123456789abcdef" for character in digest[7:])
            ):
                receipt_ref = {"path": path, "sha256": digest[7:]}
            else:
                raise ValueError("paper_terminal_gate_receipt_ref_invalid")
        elif not cross_day_terminal:
            raise ValueError("paper_terminal_gate_receipt_missing")
        status = record.get("gate_status")
        ready = record.get("gate_ready")
        blocker_count = record.get("gate_blocker_count")
        target_date = record.get("gate_target_date")
        if not cross_day_terminal and (
            not isinstance(status, str)
            or len(status) > 128
            or type(ready) is not bool
            or type(blocker_count) is not int
            or blocker_count < 0
            or not isinstance(target_date, str)
        ):
            raise ValueError("paper_terminal_gate_attempt_fields_invalid")
        if isinstance(target_date, str):
            try:
                if datetime.fromisoformat(target_date).date().isoformat() != target_date:
                    raise ValueError("paper_terminal_gate_target_date_invalid")
            except ValueError:
                raise ValueError("paper_terminal_gate_target_date_invalid")
        elif target_date is not None:
            raise ValueError("paper_terminal_gate_target_date_invalid")
        summaries.append(
            {
                "attempt": attempt,
                "target_date": target_date if isinstance(target_date, str) else None,
                "status": status if isinstance(status, str) and len(status) <= 128 else None,
                "ready": ready if type(ready) is bool else None,
                "blocker_count": blocker_count if type(blocker_count) is int and blocker_count >= 0 else None,
                "receipt_ref": receipt_ref,
            }
        )
    return summaries


def _build_terminal_receipt(
    result: Mapping[str, object],
    *,
    run_id: str,
    started_at: datetime,
    completed_at: datetime,
    exit_code: int,
) -> dict[str, object]:
    raw_status = result.get("status")
    allowed_statuses = _PAPER_TERMINAL_SUCCESS_STATUSES | frozenset(
        {"blocked", "failed", "degraded_runtime_roll_forward"}
    )
    status = raw_status if isinstance(raw_status, str) and raw_status in allowed_statuses else "failed"
    attempts = _terminal_gate_attempts(result)
    last_attempt = attempts[-1] if attempts else None
    last_status = last_attempt.get("status") if last_attempt else None
    last_ready = last_attempt.get("ready") if last_attempt else None
    if last_status in _NO_OP_GATE_STATUSES:
        dependency_status = "not_applicable"
    elif last_ready is True:
        dependency_status = "passed"
    elif last_ready is False:
        dependency_status = "blocked"
    else:
        dependency_status = "unknown"
    blocker_code = {
        "blocked": "paper_execution_blocked",
        "failed": "paper_execution_failed",
        "degraded_runtime_roll_forward": "paper_execution_roll_forward_not_ready",
    }.get(status)
    blockers = [blocker_code] if blocker_code else []
    started_text = started_at.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    completed_text = completed_at.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    gate_blocker_count = last_attempt.get("blocker_count") if last_attempt else None
    status_payload: dict[str, object] = {
        "schema_version": "paper-execution-retry-terminal-status.v1",
        "task": "baldr-paper-execution-eod-replay-daily",
        "run_id": run_id,
        "started_at": started_text,
        "completed_at": completed_text,
        "status": status,
        "exit_code": exit_code,
        "financial_qualification_status": "unknown",
        "dependency_readiness_status": dependency_status,
        "terminal_blocker_code": blocker_code,
        "gate_attempts": attempts,
        "gate_blocker_count": gate_blocker_count,
        "gate_blockers_validation": "not_copied_or_validated",
    }
    return {
        "schema_version": "paper-execution-retry-terminal-receipt.v1",
        "task": "baldr-paper-execution-eod-replay-daily",
        "run_id": run_id,
        "started_at": started_text,
        "completed_at": completed_text,
        "code_version": code_version(Path(__file__)),
        "exit_code": exit_code,
        "failure_code": blocker_code,
        "status": status,
        "blockers": blockers,
        "financial_qualification_status": "unknown",
        "dependency_readiness_status": dependency_status,
        "status_payload": status_payload,
    }


def main(argv: Sequence[str] | None = None) -> int:
    _configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    run_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc)
    try:
        result = run_scheduled(
            max_attempts=args.max_attempts,
            retry_delay_seconds=args.retry_delay_seconds,
            gate_output_root=args.gate_output_root,
        )
    except Exception:  # noqa: BLE001 - 此排程邊界仍需留下終態收據
        result = {"status": "failed", "blockers": ["paper_execution_failed"]}
    completed_at = datetime.now(timezone.utc)
    exit_code = _paper_terminal_exit_code(result)
    terminal_root = Path(args.gate_output_root).expanduser().resolve().parent / "terminal_receipts"
    try:
        receipt_path = terminal_root / f"{run_id}.json"
        receipt = _build_terminal_receipt(
            result,
            run_id=run_id,
            started_at=started_at,
            completed_at=completed_at,
            exit_code=exit_code,
        )
        result["terminal_receipt"] = write_terminal_receipt(
            receipt_path, receipt, receipt_root=terminal_root
        )
        _atomic_write_json(
            terminal_root / "latest_terminal.json",
            {
                "schema_version": "paper-execution-retry-terminal-locator.v1",
                "run_id": run_id,
                "updated_at": completed_at.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
                "terminal_receipt": result["terminal_receipt"],
                "create_only_receipt": True,
            },
        )
    except Exception:  # noqa: BLE001 - 持久化或定位失敗必須回傳非零
        exit_code = 2
        result["terminal_receipt_error"] = "paper_terminal_receipt_or_locator_persist_failed"
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return exit_code


def _configure_utf8_stdio() -> None:
    """讓 Windows 非 UTF-8 主控台也能安全顯示繁中 help/JSON。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
