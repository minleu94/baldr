"""以原保存 reader 重驗 scheduled snapshot 外部 custody；僅由組合入口明示注入。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def verify_scheduled_snapshot_source_binding_artifacts(
    snapshot_source_binding: Mapping[str, Any],
    *,
    full_cohort: Mapping[str, Any],
) -> None:
    """Reopen and verify the exact saved recommendation result and invocation.

    A caller-provided ``verified`` flag is never accepted as proof. This reader
    uses the immutable execution artifact/index and the exact invocation stdout
    bound by ``snapshot_source_binding``. It does not create directories or a
    missing result index.
    """

    import os
    import stat
    from pathlib import Path

    from app_module.recommendation.queries import _read_regular_file_no_follow
    from app_module.saved_recommendation_queries import (
        build_recommendation_execution_queries,
        execution_result_config,
    )

    output_root_value = snapshot_source_binding.get("snapshot_output_root")
    if type(output_root_value) is not str or not _is_absolute_path(output_root_value):
        raise ValueError("scheduled snapshot artifact root is missing or not absolute")
    raw_root = Path(output_root_value)
    try:
        output_root = raw_root.resolve(strict=True)
    except OSError as exc:
        raise ValueError("scheduled snapshot artifact root is unavailable") from exc
    if Path(os.path.abspath(raw_root)) != output_root:
        raise ValueError("scheduled snapshot artifact root uses a reparse or symlink path")
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    root_info = output_root.lstat()
    if (
        not stat.S_ISDIR(root_info.st_mode)
        or stat.S_ISLNK(root_info.st_mode)
        or getattr(root_info, "st_file_attributes", 0) & reparse_flag
    ):
        raise ValueError("scheduled snapshot artifact root must be a plain directory")

    invocation_path_value = snapshot_source_binding.get("invocation_output_path")
    if type(invocation_path_value) is not str or not _is_absolute_path(invocation_path_value):
        raise ValueError("scheduled snapshot invocation path is missing or not absolute")
    invocation_path = Path(invocation_path_value)
    expected_runs_root = (
        output_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "runs"
    )
    if (
        invocation_path.name != "recommendation_snapshot.stdout.bin"
        or invocation_path.parent.parent != expected_runs_root
        or Path(os.path.abspath(invocation_path)) != invocation_path.resolve(strict=True)
    ):
        raise ValueError("scheduled snapshot invocation path is outside the bound run root")
    try:
        runs_root = expected_runs_root.resolve(strict=True)
        run_dir = invocation_path.parent.resolve(strict=True)
        invocation_path = invocation_path.resolve(strict=True)
    except OSError as exc:
        raise ValueError("scheduled snapshot invocation or run directory is missing") from exc
    if run_dir.parent != runs_root or invocation_path.parent != run_dir:
        raise ValueError("scheduled snapshot invocation directory identity is invalid")
    invocation_size = snapshot_source_binding.get("invocation_output_size")
    if type(invocation_size) is not int or not 0 < invocation_size <= 8 * 1024 * 1024:
        raise ValueError("scheduled snapshot invocation size is outside its bound")
    stdout_bytes = _read_regular_file_no_follow(
        invocation_path,
        runs_root,
        max_bytes=8 * 1024 * 1024,
    )
    if (
        len(stdout_bytes) != invocation_size
        or canonical_sha256_bytes(stdout_bytes)
        != snapshot_source_binding.get("invocation_output_sha256")
    ):
        raise ValueError("scheduled snapshot invocation stdout size or hash mismatch")
    try:
        stdout_text = stdout_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("scheduled snapshot invocation stdout is not UTF-8") from exc
    invocation_receipts = _snapshot_invocation_receipts(stdout_text)
    if len(invocation_receipts) != 1:
        raise ValueError("scheduled snapshot invocation receipt is missing or ambiguous")
    invocation_receipt = invocation_receipts[0]
    if (
        invocation_receipt.get("task") != "baldr-recommendation-snapshot-daily"
        or invocation_receipt.get("result_id") != snapshot_source_binding.get("result_id")
        or invocation_receipt.get("decision_date") != snapshot_source_binding.get("decision_date")
        or invocation_receipt.get("snapshot_cohort") != dict(full_cohort)
    ):
        raise ValueError("scheduled snapshot invocation receipt identity mismatch")

    runs_dir = output_root / "recommendation" / "runs"
    if not runs_dir.is_dir() or runs_dir.is_symlink():
        raise ValueError("scheduled snapshot recommendation runs root is missing or unsafe")
    queries = build_recommendation_execution_queries(None, runs_dir=runs_dir)
    read_model = queries.get(str(snapshot_source_binding.get("result_id") or ""))
    if read_model is None:
        raise ValueError("scheduled snapshot canonical saved result is missing")
    for field_name in (
        "result_id",
        "schema_version",
        "schema_revision",
        "integrity_basis",
        "raw_artifact_sha256",
        "payload_hash",
    ):
        if getattr(read_model, field_name, None) != snapshot_source_binding.get(field_name):
            raise ValueError(f"scheduled snapshot saved artifact binding mismatch: {field_name}")
    execution = read_model.execution
    if execution is None or execution.decision is None:
        raise ValueError("scheduled snapshot saved execution is not canonical and complete")
    result_config = execution_result_config(execution)
    saved_cohort = result_config.get("snapshot_cohort")
    if not isinstance(saved_cohort, Mapping) or dict(saved_cohort) != dict(full_cohort):
        raise ValueError("scheduled snapshot saved cohort differs from the full binding")
    if (
        result_config.get("scheduled_snapshot") is not True
        or result_config.get("decision_date") != snapshot_source_binding.get("decision_date")
        or result_config.get("data_as_of_date") != snapshot_source_binding.get("data_as_of_date")
        or execution.request.as_of_date is None
        or execution.request.as_of_date.isoformat() != snapshot_source_binding.get("data_as_of_date")
        or execution.context.as_of_date is None
        or execution.context.as_of_date.isoformat() != snapshot_source_binding.get("data_as_of_date")
        or execution.context.snapshot_cohort is None
        or getattr(execution.context.snapshot_cohort, "cohort_hash", None)
        != full_cohort.get("cohort_hash")
    ):
        raise ValueError("scheduled snapshot saved execution context identity mismatch")
    saved_decision_at = execution.context.decision_at
    saved_available_at = execution.context.available_at
    if (
        saved_decision_at is None
        or saved_decision_at.tzinfo is None
        or saved_decision_at.utcoffset() is None
        or saved_decision_at.isoformat() != snapshot_source_binding.get("decision_at")
        or (
            saved_available_at.isoformat()
            if saved_available_at is not None
            else None
        )
        != snapshot_source_binding.get("available_at")
    ):
        raise ValueError("scheduled snapshot saved decision/availability clock mismatch")
    decision_symbols = tuple(
        sorted(
            str(item.stock_code).strip()
            for item in execution.decision.items
            if str(item.stock_code).strip()
        )
    )
    expected_symbols = _normalize_exact_symbols(full_cohort.get("eligible_symbols"))
    if decision_symbols != expected_symbols:
        raise ValueError("scheduled snapshot decision rows do not cover its eligible cohort")

def canonical_sha256_bytes(payload: bytes) -> str:
    """Return the standard prefixed SHA-256 digest for exact file bytes."""

    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _snapshot_invocation_receipts(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    matches: list[dict[str, Any]] = []
    position = 0
    while position < len(text):
        start = text.find("{", position)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            position = start + 1
            continue
        position = end
        if (
            isinstance(value, dict)
            and value.get("task") == "baldr-recommendation-snapshot-daily"
        ):
            matches.append(value)
    return matches


def _normalize_exact_symbols(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("symbol list is missing")
    symbols = tuple(value)
    if any(type(symbol) is not str or not symbol or symbol.strip() != symbol for symbol in symbols):
        raise ValueError("symbols must be non-empty, trimmed strings")
    if symbols != tuple(sorted(symbols)) or len(symbols) != len(set(symbols)):
        raise ValueError("symbols must be sorted and unique")
    return symbols


def _is_absolute_path(value: str) -> bool:
    from pathlib import PurePath
    from pathlib import PureWindowsPath

    return PurePath(value).is_absolute() or PureWindowsPath(value).is_absolute()
