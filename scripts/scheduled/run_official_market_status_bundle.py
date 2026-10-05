"""執行歷史市場事件回補與獨立的現況狀態觀測。"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable, Mapping, Sequence
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_module.current_market_status_observation import (  # noqa: E402
    CurrentMarketStatusError,
    CurrentMarketStatusReader,
)


Runner = Callable[..., subprocess.CompletedProcess[bytes | str]]
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _last_status_json(*outputs: str) -> dict[str, object] | None:
    for output in outputs:
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("status"), str):
            return payload
        for line in reversed(output.splitlines()):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and isinstance(payload.get("status"), str):
                return payload
    return None


def _run_child(
    command: Sequence[str],
    *,
    runner: Runner,
    env: Mapping[str, str],
) -> dict[str, object]:
    try:
        completed = runner(
            list(command),
            cwd=str(REPO_ROOT),
            env=dict(env),
            capture_output=True,
            check=False,
        )
    except OSError as error:
        return {
            "return_code": None,
            "status": "launch_failed",
            "error": f"{type(error).__name__}: {error}",
            "status_payload": None,
            "stdout_sha256": "sha256:" + hashlib.sha256(b"").hexdigest(),
            "stderr_sha256": "sha256:" + hashlib.sha256(b"").hexdigest(),
        }
    raw_stdout = completed.stdout or b""
    raw_stderr = completed.stderr or b""
    stdout_bytes = raw_stdout if isinstance(raw_stdout, bytes) else raw_stdout.encode("utf-8")
    stderr_bytes = raw_stderr if isinstance(raw_stderr, bytes) else raw_stderr.encode("utf-8")
    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    payload = _last_status_json(stdout, stderr)
    return {
        "return_code": int(completed.returncode),
        "status": (
            str(payload.get("status"))
            if payload is not None
            else "missing_structured_status"
        ),
        "status_payload": payload,
        "stdout_sha256": "sha256:" + hashlib.sha256(stdout_bytes).hexdigest(),
        "stdout_bytes": len(stdout_bytes),
        "stderr_sha256": "sha256:" + hashlib.sha256(stderr_bytes).hexdigest(),
        "stderr_bytes": len(stderr_bytes),
        "stderr_tail": stderr[-4000:] or None,
    }


def _find_exact_historical_receipt(
    output_root: Path,
    payload: object,
    *,
    exclude_paths: set[Path] | None = None,
) -> dict[str, str] | None:
    if not isinstance(payload, dict):
        return None
    status_root = output_root / "scheduled" / "official_market_events"
    if not status_root.is_dir():
        return None
    for candidate in status_root.glob("*.json"):
        if (
            candidate.name == "latest_status.json"
            or candidate.is_symlink()
            or (exclude_paths is not None and candidate.resolve() in exclude_paths)
        ):
            continue
        try:
            if json.loads(candidate.read_text(encoding="utf-8")) == payload:
                return {
                    "path": str(candidate),
                    "sha256": _sha256_file(candidate),
                }
        except (OSError, json.JSONDecodeError):
            continue
    return None


def _historical_capture_evidence(
    output_root: Path,
    child: dict[str, object],
) -> dict[str, object]:
    payload = child.get("status_payload")
    receipt = child.get("receipt")
    evidence: dict[str, object] = {"validation": "invalid_or_missing"}
    if not isinstance(payload, dict) or not isinstance(receipt, dict):
        evidence["validation_error"] = "missing_child_status_or_exact_receipt"
        return evidence
    try:
        receipt_path = _contained_file(receipt.get("path"), output_root.resolve())
        receipt_sha = _sha256_file(receipt_path)
        if receipt.get("sha256") != receipt_sha:
            raise ValueError("historical_status_receipt_hash_mismatch")
        receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt_payload != payload:
            raise ValueError("historical_status_receipt_payload_mismatch")
        evidence.update(
            {
                "status_receipt_path": str(receipt_path),
                "status_receipt_sha256": receipt_sha,
                "status_receipt_matches_child_stdout": True,
                "child_stdout_sha256": child.get("stdout_sha256"),
            }
        )
        if payload.get("status") == "published":
            manifest_path = _contained_file(
                payload.get("manifest_path"),
                (output_root / "release_v4" / "official_market_events").resolve(),
            )
            manifest_sha = _sha256_file(manifest_path)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                payload.get("manifest_file_hash") != manifest_sha
                or payload.get("manifest_hash") != manifest.get("manifest_hash")
            ):
                raise ValueError("historical_manifest_hash_or_run_mismatch")
            evidence.update(
                {
                    "manifest_path": str(manifest_path),
                    "manifest_file_sha256": manifest_sha,
                    "manifest_hash": payload.get("manifest_hash"),
                    "canonical_events": manifest.get("canonical_events"),
                }
            )
        evidence["validation"] = "verified"
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        evidence["validation_error"] = f"{type(error).__name__}: {error}"
    return evidence


def _json_content_hash(payload: Mapping[str, object]) -> str:
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _contained_file(path_value: object, root: Path) -> Path:
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("artifact_path_missing")
    candidate = Path(path_value)
    if candidate.is_symlink():
        raise ValueError("artifact_path_is_symlink")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("artifact_path_escapes_output_root")
    if not resolved.is_file():
        raise ValueError("artifact_path_not_file")
    return resolved


def _validate_prior_failure_attempt(
    attempt: object,
    *,
    market: str,
    valuation_root: Path,
    wrapper_run_id: str,
) -> dict[str, object]:
    if not isinstance(attempt, dict):
        raise ValueError(f"{market}_prior_failure_attempt_not_object")
    required = {
        "source_id",
        "requested_url",
        "final_url",
        "status",
        "raw_response_path",
        "raw_response_sha256",
        "raw_response_bytes",
        "receipt_path",
        "receipt_sha256",
        "diagnostic",
        "captured_at",
    }
    if not required.issubset(attempt):
        raise ValueError(f"{market}_prior_failure_attempt_fields_missing")
    if (
        attempt.get("status") != "failed"
        or not isinstance(attempt.get("source_id"), str)
        or not attempt["source_id"]
        or not isinstance(attempt.get("requested_url"), str)
        or not attempt["requested_url"].startswith("https://")
        or not isinstance(attempt.get("final_url"), str)
        or not attempt["final_url"].startswith("https://")
        or not isinstance(attempt.get("diagnostic"), str)
        or not attempt["diagnostic"]
    ):
        raise ValueError(f"{market}_prior_failure_attempt_metadata_invalid")

    raw_path_value = attempt.get("raw_response_path")
    raw_digest = attempt.get("raw_response_sha256")
    raw_size = attempt.get("raw_response_bytes")
    receipt_path_value = attempt.get("receipt_path")
    receipt_digest = attempt.get("receipt_sha256")
    captured_at = attempt.get("captured_at")
    has_raw = raw_path_value is not None
    has_receipt = receipt_path_value is not None
    if has_raw != has_receipt:
        raise ValueError(f"{market}_prior_failure_artifact_pair_incomplete")

    attempt_evidence: dict[str, object] = {
        "source_id": attempt["source_id"],
        "requested_url": attempt["requested_url"],
        "final_url": attempt["final_url"],
        "status": "failed",
        "raw_response_path": None,
        "raw_response_sha256": raw_digest,
        "raw_response_bytes": raw_size,
        "receipt_path": None,
        "receipt_sha256": receipt_digest,
        "captured_at": captured_at,
        "diagnostic": attempt["diagnostic"],
    }

    if not has_raw:
        # A connection failure has no body. An oversized body is deliberately
        # not persisted; preserve only its digest/count and explicit size-limit
        # diagnostic, never accepting a partially written file as a receipt.
        no_body = raw_digest is None and raw_size is None and captured_at is None
        oversized = (
            raw_digest is not None
            and isinstance(raw_digest, str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", raw_digest) is not None
            and isinstance(raw_size, int)
            and not isinstance(raw_size, bool)
            and raw_size > 32 * 1024 * 1024
            and isinstance(captured_at, str)
            and "exceeds size limit" in str(attempt["diagnostic"]).lower()
        )
        if (
            raw_digest is not None and not oversized
            or raw_size is not None and not oversized
            or captured_at is not None and not oversized
            or receipt_digest is not None
            or not (no_body or oversized)
        ):
            raise ValueError(f"{market}_prior_failure_without_body_receipt_inconsistent")
        return attempt_evidence

    if (
        not isinstance(raw_digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", raw_digest) is None
        or not isinstance(raw_size, int)
        or isinstance(raw_size, bool)
        or raw_size < 0
        or not isinstance(receipt_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", receipt_digest) is None
        or not isinstance(captured_at, str)
    ):
        raise ValueError(f"{market}_prior_failure_artifact_metadata_invalid")
    try:
        captured_time = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{market}_prior_failure_capture_time_invalid") from error
    if captured_time.tzinfo is None or captured_time.utcoffset() is None:
        raise ValueError(f"{market}_prior_failure_capture_time_naive")

    raw_path = _contained_file(raw_path_value, valuation_root)
    receipt_path = _contained_file(receipt_path_value, valuation_root)
    raw_bytes = raw_path.read_bytes()
    receipt_bytes = receipt_path.read_bytes()
    if (
        raw_path.name != "raw_response.bin"
        or "attempts" not in raw_path.parts
        or raw_path.parent != receipt_path.parent
        or receipt_path.name != "receipt.json"
        or len(raw_bytes) != raw_size
        or "sha256:" + hashlib.sha256(raw_bytes).hexdigest() != raw_digest
        or hashlib.sha256(receipt_bytes).hexdigest() != receipt_digest
    ):
        raise ValueError(f"{market}_prior_failure_raw_or_receipt_hash_mismatch")
    expected_attempt_root = (
        valuation_root
        / "runs"
        / wrapper_run_id
        / "markets"
        / market
        / "attempts"
    ).resolve()
    if not receipt_path.parent.is_relative_to(expected_attempt_root):
        raise ValueError(f"{market}_prior_failure_receipt_wrong_run_or_market")
    receipt = json.loads(receipt_bytes.decode("utf-8"))
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema_version") != "official-current-valuation-market-failure.v1"
        or receipt.get("status") != "failed"
        or receipt.get("market") != market
        or receipt.get("source_id") != attempt.get("source_id")
        or receipt.get("requested_url") != attempt.get("requested_url")
        or receipt.get("final_url") != attempt.get("final_url")
        or receipt.get("diagnostic") != attempt.get("diagnostic")
        or receipt.get("body_completed_at") != captured_at
        or receipt.get("raw_response_path") != raw_path.name
        or receipt.get("raw_response_sha256") != raw_digest
        or receipt.get("raw_response_bytes") != raw_size
        or not isinstance(receipt.get("attempt_id"), str)
        or receipt_path.parent.name != receipt.get("attempt_id")
        or receipt.get("formal_pit_eligible") is not False
        or receipt.get("historical_pit_eligible") is not False
        or receipt.get("content_sha256") != _json_content_hash(receipt)
    ):
        raise ValueError(f"{market}_prior_failure_receipt_content_invalid")
    attempt_evidence.update(
        {
            "raw_response_path": str(raw_path),
            "receipt_path": str(receipt_path),
        }
    )
    return attempt_evidence


def _valuation_capture_evidence(
    output_root: Path,
    child: dict[str, object],
    *,
    wrapper_run_id: str,
) -> dict[str, object]:
    payload = child.get("status_payload")
    evidence: dict[str, object] = {"validation": "invalid_or_missing"}
    if not isinstance(payload, dict):
        evidence["validation_error"] = "missing_child_status"
        return evidence
    try:
        valuation_root = (output_root / "current_valuation").resolve()
        run_id = str(payload.get("run_id") or "")
        if (
            payload.get("schema_version") != "official-current-valuation-run.v1"
            or payload.get("wrapper_run_id") != wrapper_run_id
            or run_id != wrapper_run_id
            or payload.get("formal_pit_eligible") is not False
            or payload.get("historical_pit_eligible") is not False
        ):
            raise ValueError("terminal_receipt_scope_or_run_binding_invalid")

        terminal_path = _contained_file(payload.get("receipt_path"), valuation_root)
        expected_terminal = (
            valuation_root / "runs" / wrapper_run_id / "receipt.json"
        ).resolve()
        if terminal_path != expected_terminal:
            raise ValueError("terminal_receipt_path_not_bound_to_wrapper_run")
        terminal_bytes = terminal_path.read_bytes()
        terminal_sha = hashlib.sha256(terminal_bytes).hexdigest()
        if payload.get("receipt_sha256") != terminal_sha:
            raise ValueError("terminal_receipt_file_hash_mismatch")
        terminal = json.loads(terminal_bytes.decode("utf-8"))
        if (
            not isinstance(terminal, dict)
            or terminal.get("schema_version") != "official-current-valuation-run.v1"
            or terminal.get("status") != payload.get("status")
            or terminal.get("run_id") != run_id
            or terminal.get("wrapper_run_id") != wrapper_run_id
            or terminal.get("content_sha256") != _json_content_hash(terminal)
            or terminal.get("markets") != payload.get("markets")
        ):
            # The CLI projection intentionally renames per-market receipt keys.
            if not isinstance(terminal, dict):
                raise ValueError("terminal_receipt_not_object")
            if (
                terminal.get("schema_version") != "official-current-valuation-run.v1"
                or terminal.get("status") != payload.get("status")
                or terminal.get("run_id") != run_id
                or terminal.get("wrapper_run_id") != wrapper_run_id
                or terminal.get("content_sha256") != _json_content_hash(terminal)
            ):
                raise ValueError("terminal_receipt_content_or_binding_invalid")

        terminal_markets = terminal.get("markets")
        stdout_markets = payload.get("markets")
        if not isinstance(terminal_markets, list) or not isinstance(stdout_markets, list):
            raise ValueError("market_receipts_missing")
        expected_markets = {"twse", "tpex"}
        if (
            {str(row.get("market")) for row in terminal_markets if isinstance(row, dict)}
            != expected_markets
            or {str(row.get("market")) for row in stdout_markets if isinstance(row, dict)}
            != expected_markets
            or len(terminal_markets) != 2
            or len(stdout_markets) != 2
        ):
            raise ValueError("market_coverage_not_exact")

        market_evidence: list[dict[str, object]] = []
        for terminal_row in terminal_markets:
            if not isinstance(terminal_row, dict):
                raise ValueError("market_receipt_not_object")
            market = str(terminal_row.get("market") or "")
            stdout_row = next(
                row
                for row in stdout_markets
                if isinstance(row, dict) and row.get("market") == market
            )
            if (
                stdout_row.get("status") != terminal_row.get("status")
                or stdout_row.get("source_date") != terminal_row.get("source_date")
                or stdout_row.get("available_at") != terminal_row.get("available_at")
                or stdout_row.get("raw_response_sha256")
                != terminal_row.get("raw_response_sha256")
                or stdout_row.get("raw_response_path")
                != terminal_row.get("raw_response_path")
                or stdout_row.get("receipt_path")
                != terminal_row.get("receipt_path")
                or stdout_row.get("receipt_sha256")
                != terminal_row.get("receipt_sha256")
                or stdout_row.get("failure_receipt_path")
                != terminal_row.get("failure_receipt_path")
                or stdout_row.get("failure_receipt_sha256")
                != terminal_row.get("failure_receipt_sha256")
                or stdout_row.get("prior_failure_attempts", [])
                != terminal_row.get("prior_failure_attempts", [])
            ):
                raise ValueError(f"{market}_stdout_terminal_market_mismatch")

            prior_attempts = terminal_row.get("prior_failure_attempts", [])
            if not isinstance(prior_attempts, list):
                raise ValueError(f"{market}_prior_failure_attempts_not_list")
            verified_prior_attempts = [
                _validate_prior_failure_attempt(
                    attempt,
                    market=market,
                    valuation_root=valuation_root,
                    wrapper_run_id=wrapper_run_id,
                )
                for attempt in prior_attempts
            ]

            raw_path_value = terminal_row.get("raw_response_path")
            raw_digest = terminal_row.get("raw_response_sha256")
            if raw_path_value is not None:
                raw_path = _contained_file(raw_path_value, valuation_root)
                raw_bytes = raw_path.read_bytes()
                raw_actual = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
                if raw_digest != raw_actual or terminal_row.get("raw_response_bytes") != len(raw_bytes):
                    raise ValueError(f"{market}_raw_response_hash_or_size_mismatch")
            else:
                raw_path = None
                if raw_digest is not None:
                    raise ValueError(f"{market}_raw_response_path_missing")

            if terminal_row.get("status") == "captured":
                receipt_path = _contained_file(terminal_row.get("receipt_path"), valuation_root)
                receipt_digest = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
                if (
                    stdout_row.get("receipt_path") != str(receipt_path)
                    or stdout_row.get("receipt_sha256") != receipt_digest
                    or terminal_row.get("receipt_sha256") != receipt_digest
                    or terminal_row.get("failure_receipt_path") is not None
                ):
                    raise ValueError(f"{market}_capture_receipt_hash_mismatch")
                market_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if (
                    market_receipt.get("schema_version") != "official-current-valuation-capture.v1"
                    or market_receipt.get("source_authority") != market
                    or market_receipt.get("run_id") != run_id
                    or market_receipt.get("wrapper_run_id") != wrapper_run_id
                    or market_receipt.get("source_date") != terminal_row.get("source_date")
                    or market_receipt.get("available_at") != terminal_row.get("available_at")
                    or market_receipt.get("source_row_count") != terminal_row.get("source_row_count")
                    or market_receipt.get("unique_stock_count")
                    != terminal_row.get("unique_stock_count")
                    or market_receipt.get("raw_response_sha256") != raw_digest
                    or market_receipt.get("content_sha256")
                    != _json_content_hash(market_receipt)
                    or raw_path != (receipt_path.parent / "raw_response.bin").resolve()
                ):
                    raise ValueError(f"{market}_capture_receipt_content_invalid")
            elif terminal_row.get("status") == "failed":
                failure_path = _contained_file(
                    terminal_row.get("failure_receipt_path"), valuation_root
                )
                failure_digest = hashlib.sha256(failure_path.read_bytes()).hexdigest()
                if (
                    stdout_row.get("failure_receipt_path") != str(failure_path)
                    or stdout_row.get("failure_receipt_sha256") != failure_digest
                    or terminal_row.get("failure_receipt_sha256") != failure_digest
                    or failure_path.parent != (valuation_root / "runs" / wrapper_run_id / "markets" / market).resolve()
                ):
                    raise ValueError(f"{market}_failure_receipt_hash_mismatch")
                market_receipt = json.loads(failure_path.read_text(encoding="utf-8"))
                if (
                    market_receipt.get("schema_version")
                    != "official-current-valuation-market-failure.v1"
                    or market_receipt.get("market") != market
                    or market_receipt.get("status") != "failed"
                    or market_receipt.get("raw_response_sha256") != raw_digest
                    or market_receipt.get("content_sha256")
                    != _json_content_hash(market_receipt)
                ):
                    raise ValueError(f"{market}_failure_receipt_content_invalid")
            else:
                raise ValueError(f"{market}_market_status_invalid")

            market_evidence.append(
                {
                    "market": market,
                    "status": terminal_row.get("status"),
                    "source_date": terminal_row.get("source_date"),
                    "available_at": terminal_row.get("available_at"),
                    "raw_response_path": str(raw_path) if raw_path else None,
                    "raw_response_sha256": raw_digest,
                    "capture_receipt_path": terminal_row.get("receipt_path"),
                    "capture_receipt_sha256": terminal_row.get("receipt_sha256"),
                    "failure_receipt_path": terminal_row.get("failure_receipt_path"),
                    "failure_receipt_sha256": terminal_row.get("failure_receipt_sha256"),
                    "prior_failure_attempts": verified_prior_attempts,
                }
            )
        evidence.update(
            {
                "validation": "verified",
                "terminal_receipt_path": str(terminal_path),
                "terminal_receipt_sha256": "sha256:" + terminal_sha,
                "terminal_run_id": run_id,
                "wrapper_run_id": wrapper_run_id,
                "status": terminal.get("status"),
                "formal_pit_eligible": terminal.get("formal_pit_eligible"),
                "historical_pit_eligible": terminal.get("historical_pit_eligible"),
                "markets": market_evidence,
            }
        )
    except (OSError, TypeError, ValueError, StopIteration, json.JSONDecodeError) as error:
        evidence["validation_error"] = f"{type(error).__name__}: {error}"
    return evidence


def _current_capture_evidence(
    output_root: Path,
    child: dict[str, object],
) -> dict[str, object]:
    payload = child.get("status_payload")
    if not isinstance(payload, dict):
        return {"pointer_validation": "missing_child_status"}
    output_dir = output_root / "release_v4" / "current_market_status"
    pointer_path = output_dir / "current_market_status_pointer.json"
    evidence: dict[str, object] = {"pointer_path": str(pointer_path)}
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        reader = CurrentMarketStatusReader.from_pointer(pointer_path)
        run_id = str(pointer.get("run_id") or "")
        snapshot_rel = str(pointer.get("snapshot_path") or "")
        manifest_rel = str(pointer.get("manifest_path") or "")
        snapshot_path = (output_dir / snapshot_rel).resolve()
        manifest_path = (output_dir / manifest_rel).resolve()
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        summary_snapshot = Path(str(payload.get("snapshot_path") or "")).resolve()
        summary_matches = summary_snapshot == snapshot_path
        run_matches = str(snapshot.get("run_id") or "") == run_id
        pointer_matches_child = summary_matches and run_matches
        evidence.update(
            {
                "pointer_validation": "verified",
                "pointer_sha256": _sha256_file(pointer_path),
                "run_id": run_id,
                "snapshot_path": str(snapshot_path),
                "snapshot_sha256": _sha256_file(snapshot_path),
                "manifest_path": str(manifest_path),
                "manifest_sha256": _sha256_file(manifest_path),
                "snapshot_run_id_matches_pointer": run_matches,
                "snapshot_path_matches_child": summary_matches,
                "pointer_matches_child_run": pointer_matches_child,
                "reader_security_count": len(snapshot.get("securities", [])),
                "reader_contract": "current_only_pit_ineligible",
                "reader_scope": reader.get("2323").scope,
            }
        )
        if not pointer_matches_child:
            evidence["pointer_validation"] = "valid_pointer_does_not_match_child_run"
        # 經由公開型別化契約讀取固定指標；不依缺少報價推論，也不猜測最新目錄。
        evidence["reader_unknown_example"] = reader.get("0000").listing_status
    except (OSError, TypeError, ValueError, CurrentMarketStatusError, json.JSONDecodeError) as error:
        evidence.update(
            {
                "pointer_validation": "invalid_or_missing",
                "validation_error": f"{type(error).__name__}: {error}",
            }
        )
    return evidence


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 不重複目標檔名，讓深層 Windows 輸出根仍可安全原子替換。
    temporary = path.parent / f".{uuid4().hex}.tmp"
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _write_json_create_only(path: Path, payload: object) -> None:
    """以 exclusive-create 寫入不可變 run receipt。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    # O_EXCL 讓最後發布本身拒絕競態中的既有目標；若寫入中斷，run pointer
    # 尚未更新，留下的檔案會使同一 run id fail closed，而不覆蓋部分證據。
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(serialized)
        handle.flush()
        os.fsync(handle.fileno())


def run_bundle(
    *,
    output_root: Path,
    runner: Runner = subprocess.run,
    wrapper_run_id: str | None = None,
) -> tuple[dict[str, object], Path]:
    """獨立執行兩個步驟，並發布一份不可變的 wrapper 收據。"""
    resolved_output_root = Path(output_root).expanduser().resolve()
    run_id = wrapper_run_id or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        + "-"
        + uuid4().hex[:12]
    )
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("wrapper_run_id must be a bounded ASCII run identifier")
    status_root = resolved_output_root / "scheduled" / "official_market_events_wrapper"
    runs_root = status_root / "runs"
    run_path = runs_root / f"{run_id}.json"
    # 避免重用 ID 時先啟動子程序並在末端改寫既有 receipt。這只是早期拒絕；
    # 最終 exclusive-create 仍負責處理檢查後到發布前的競態。
    if run_path.exists() or run_path.is_symlink():
        raise FileExistsError(f"immutable wrapper run receipt already exists: {run_path}")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    historical_command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "scheduled" / "run_official_market_event_backfill.py"),
        "--output-root",
        str(resolved_output_root),
    ]
    current_output = resolved_output_root / "release_v4" / "current_market_status"
    current_command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "refresh_current_market_status_observation.py"),
        "--output-dir",
        str(current_output),
    ]
    valuation_command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "capture_current_official_valuation.py"),
        "--output-root",
        str(resolved_output_root),
        "--wrapper-run-id",
        run_id,
    ]

    started_at = datetime.now(timezone.utc).isoformat()
    history_status_root = resolved_output_root / "scheduled" / "official_market_events"
    history_paths_before = (
        {
            path.resolve()
            for path in history_status_root.glob("*.json")
            if path.name != "latest_status.json" and not path.is_symlink()
        }
        if history_status_root.is_dir()
        else set()
    )
    historical = _run_child(historical_command, runner=runner, env=env)
    historical_payload = historical.get("status_payload")
    historical["wrapper_run_id"] = run_id
    historical["receipt"] = _find_exact_historical_receipt(
        resolved_output_root,
        historical_payload,
        exclude_paths=history_paths_before,
    )
    historical["capture_evidence"] = _historical_capture_evidence(
        resolved_output_root,
        historical,
    )

    # 即使歷史發布失敗仍要執行現況擷取；兩邊狀態分開保存，並驗證 canonical
    # 指標是否綁定到這次子程序所建立的 run。
    current = _run_child(current_command, runner=runner, env=env)
    current["wrapper_run_id"] = run_id
    current["capture_evidence"] = _current_capture_evidence(
        resolved_output_root,
        current,
    )

    # Keep valuation independent; an earlier child's failure cannot suppress
    # this separate current-source capture.
    valuation = _run_child(valuation_command, runner=runner, env=env)
    valuation["wrapper_run_id"] = run_id
    valuation["capture_evidence"] = _valuation_capture_evidence(
        resolved_output_root,
        valuation,
        wrapper_run_id=run_id,
    )

    history_evidence = historical.get("capture_evidence")
    history_ok = (
        historical.get("return_code") == 0
        and historical.get("status") == "published"
        and isinstance(historical.get("receipt"), dict)
        and isinstance(history_evidence, dict)
        and history_evidence.get("validation") == "verified"
    )
    current_payload = current.get("status_payload")
    current_evidence = current.get("capture_evidence")
    current_ok = (
        current.get("return_code") == 0
        and current.get("status") == "current_market_status_captured"
        and isinstance(current_payload, dict)
        and current_payload.get("partial_failure") is False
        and isinstance(current_evidence, dict)
        and current_evidence.get("pointer_validation") == "verified"
        and current_evidence.get("pointer_matches_child_run") is True
    )
    valuation_evidence = valuation.get("capture_evidence")
    valuation_ok = (
        valuation.get("return_code") == 0
        and valuation.get("status") == "captured"
        and isinstance(valuation_evidence, dict)
        and valuation_evidence.get("validation") == "verified"
        and valuation_evidence.get("status") == "captured"
        and valuation_evidence.get("wrapper_run_id") == run_id
        and all(
            isinstance(row, dict) and row.get("status") == "captured"
            for row in valuation_evidence.get("markets", [])
        )
    )
    overall_status = (
        "succeeded" if history_ok and current_ok and valuation_ok else "failed"
    )
    receipt: dict[str, object] = {
        "schema_version": "scheduled-official-market-status-bundle.v1",
        "wrapper_run_id": run_id,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "output_root": str(resolved_output_root),
        "historical_official_market_events": historical,
        "current_market_status_observation": current,
        "current_official_valuation": valuation,
        "overall_status": overall_status,
        "overall_return_code": 0 if overall_status == "succeeded" else 1,
        "history_status_and_valuation_are_independent_steps": True,
        "formal_historical_status_receipts_are_not_overwritten": True,
    }
    _write_json_create_only(run_path, receipt)
    pointer = {
        "schema_version": "scheduled-official-market-events-wrapper-pointer.v1",
        "wrapper_run_id": run_id,
        "status_path": str(Path("runs") / run_path.name),
        "status_sha256": _sha256_file(run_path),
        "overall_status": overall_status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write_json(status_root / "latest_status.json", pointer)
    reported_receipt = {
        **receipt,
        "receipt_path": str(run_path),
        "receipt_sha256": _sha256_file(run_path),
    }
    return reported_receipt, run_path


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    receipt, _ = run_bundle(output_root=args.output_root)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return_code = receipt.get("overall_return_code")
    return return_code if isinstance(return_code, int) else 1


if __name__ == "__main__":
    raise SystemExit(main())
