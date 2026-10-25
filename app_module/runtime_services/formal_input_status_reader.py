"""唯讀恢復 Formal producer 最近一次非休市終態。"""

from __future__ import annotations

from collections import deque
import hashlib
import json
from pathlib import Path
from typing import Mapping


def read_last_non_skipped_attempt(status_path: Path) -> dict[str, object] | None:
    """從 latest status 或經 receipt 驗證的 append-only log 取得最近終態。"""

    try:
        previous_value = json.loads(Path(status_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        previous_value = None
    if isinstance(previous_value, Mapping):
        previous = dict(previous_value)
        prior_summary = previous.get("last_non_skipped_attempt")
        if isinstance(prior_summary, Mapping):
            prior_status = prior_summary.get("status")
            if isinstance(prior_status, str) and prior_status != "skipped_non_trading_day":
                return dict(prior_summary)
        status_text = previous.get("status")
        if isinstance(status_text, str) and status_text != "skipped_non_trading_day":
            blockers = previous.get("blockers")
            receipt = previous.get("terminal_receipt")
            return {
                "run_id": previous.get("run_id"),
                "status": status_text,
                "observed_at": previous.get("observed_at"),
                "completed_at": previous.get("completed_at"),
                "exit_code": previous.get("exit_code"),
                "blockers": list(blockers) if isinstance(blockers, list) else [],
                "terminal_receipt": dict(receipt) if isinstance(receipt, Mapping) else None,
            }
    return read_last_non_skipped_attempt_from_log(Path(status_path))


def read_last_non_skipped_attempt_from_log(
    status_path: Path,
) -> dict[str, object] | None:
    """由 append-only attempt log 與 hash-bound terminal receipt 還原終態。"""

    attempt_log_path = status_path.with_name("attempts.jsonl")
    try:
        with attempt_log_path.open("r", encoding="utf-8") as stream:
            recent_lines = deque(stream, maxlen=10_000)
    except (OSError, UnicodeError):
        return None
    try:
        receipt_root = (status_path.parent / "receipts").resolve()
    except OSError:
        return None
    for line in reversed(recent_lines):
        try:
            attempt_value = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(attempt_value, Mapping):
            continue
        attempt = dict(attempt_value)
        status_text = attempt.get("status")
        run_id = attempt.get("run_id")
        if (
            attempt.get("phase") != "terminal_persistence_completed"
            or not isinstance(status_text, str)
            or status_text == "skipped_non_trading_day"
            or not isinstance(run_id, str)
            or not run_id
        ):
            continue
        receipt_ref = attempt.get("terminal_receipt")
        if not isinstance(receipt_ref, Mapping):
            continue
        receipt_path_value = receipt_ref.get("path")
        receipt_sha256 = receipt_ref.get("sha256")
        if not isinstance(receipt_path_value, str) or not isinstance(receipt_sha256, str):
            continue
        try:
            receipt_path = Path(receipt_path_value).resolve()
            if receipt_path.parent != receipt_root:
                continue
            receipt_bytes = receipt_path.read_bytes()
            if "sha256:" + hashlib.sha256(receipt_bytes).hexdigest() != receipt_sha256:
                continue
            receipt_value = json.loads(receipt_bytes.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            continue
        if (
            not isinstance(receipt_value, Mapping)
            or receipt_value.get("schema_version")
            != "formal-input-producer-terminal-receipt.v1"
            or receipt_value.get("run_id") != run_id
            or receipt_value.get("status") != status_text
        ):
            continue
        status_payload = receipt_value.get("status_payload")
        receipt_blockers = receipt_value.get("blockers")
        attempt_blockers = attempt.get("blockers")
        observability_blockers = attempt.get("observability_blockers")
        blockers = [
            item
            for source in (receipt_blockers, attempt_blockers, observability_blockers)
            if isinstance(source, list)
            for item in source
            if isinstance(item, str)
        ]
        return {
            "run_id": run_id,
            "status": status_text,
            "observed_at": status_payload.get("observed_at")
            if isinstance(status_payload, Mapping)
            else attempt.get("observed_at"),
            "completed_at": receipt_value.get("completed_at"),
            "exit_code": attempt.get("exit_code"),
            "blockers": list(dict.fromkeys(blockers)),
            "terminal_receipt": {
                "path": str(receipt_path),
                "sha256": receipt_sha256,
            },
        }
    return None
