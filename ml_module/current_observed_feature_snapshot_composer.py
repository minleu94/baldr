"""Bounded, hash-bound composition for current-observed cohorts over 16 symbols.

The G6 provider deliberately accepts at most sixteen symbols per invocation.
This module composes those exact v1 observations into one complete v2 feature
snapshot without changing the meaning of any per-batch source-table hash.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Mapping, Sequence


FEATURE_SNAPSHOT_V1 = "recommendation-current-observed-feature-snapshot.v1"
FEATURE_SNAPSHOT_V2 = "recommendation-current-observed-feature-snapshot.v2"
FEATURE_BATCH_V1 = "recommendation-current-observed-feature-batch.v1"
FEATURE_COMPOSITION_V1 = "recommendation-current-observed-feature-batch-composition.v1"
SCHEDULED_COHORT_V1 = "scheduled-recommendation-snapshot-cohort.v1"
ENTRY_OBSERVATION_V1 = "recommendation-current-observed-entry-observation.v1"

MAX_SYMBOLS_PER_BATCH = 16
MAX_TOTAL_SYMBOLS = 50
SOURCE_TABLES = (
    "daily_prices",
    "technical_indicators",
    "market_indices",
    "industry_indices",
)

_V1_COMMON_FIELDS = (
    "status",
    "verified",
    "decision_date",
    "feature_as_of_date",
    "history_start_date",
    "observed_at",
    "cycle_source_date",
    "cycle_id",
    "raw_run_id",
    "discovery_raw_run_id",
    "discovery_cycle_terminal_path",
    "discovery_cycle_terminal_sha256",
    "discovery_cycle_terminal_status",
    "reuse_source_identity",
    "discovery_status_path",
    "discovery_status_sha256",
    "discovery_status_bytes_base64",
    "cycle_terminal_path",
    "cycle_terminal_sha256",
    "snapshot_database_path",
    "snapshot_database_sha256",
    "snapshot_receipt_path",
    "snapshot_receipt_sha256",
    "source_context_envelope_path",
    "source_context_envelope_sha256",
    "feature_registry_id",
    "feature_registry_hash",
    "feature_schema_hash",
    "current_restated",
    "historical_pit_eligible",
    "formal_training_allowed",
    "research_only",
    "reason",
)
_V1_LOCAL_FIELDS = (
    "schema_version",
    "symbols",
    "rows",
    "row_count",
    "rows_sha256",
    "source_rows_sha256_by_table",
    "entry_observation",
    "content_sha256",
)
_V1_FIELDS = frozenset((*_V1_COMMON_FIELDS, *_V1_LOCAL_FIELDS))
_BATCH_FIELDS = frozenset(
    {
        "schema_version",
        "ordinal",
        "symbols",
        "row_count",
        "rows_sha256",
        "child_snapshot_content_sha256",
        "source_rows_sha256_by_table",
        "entry_observation",
        "batch_sha256",
    }
)
_COMPOSITION_FIELDS = frozenset(
    {
        "schema_version",
        "scope_mode",
        "cohort_hash",
        "full_cohort",
        "snapshot_source_binding",
        "max_symbols_per_batch",
        "max_total_symbols",
        "batch_count",
        "batches",
        "symbols",
        "rows_sha256",
        "cycle_id",
        "raw_run_id",
        "cycle_source_date",
        "decision_date",
        "feature_as_of_date",
        "observed_at",
        "cycle_terminal_path",
        "cycle_terminal_sha256",
        "snapshot_database_path",
        "snapshot_database_sha256",
        "snapshot_receipt_path",
        "snapshot_receipt_sha256",
        "source_context_envelope_path",
        "source_context_envelope_sha256",
        "feature_registry_id",
        "feature_registry_hash",
        "feature_schema_hash",
        "composition_sha256",
    }
)
_SCHEDULED_SCOPE_MODE = "verified_scheduled_snapshot_cohort"


def canonical_sha256(payload: Any) -> str:
    """Hash the repository's canonical JSON representation with a prefix."""

    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("payload is not canonical-JSON serializable") from exc
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def partition_current_observed_symbols(
    symbols: Sequence[str],
) -> tuple[tuple[str, ...], ...]:
    """Return deterministic sorted chunks; reject duplicates and scopes over 50."""

    if isinstance(symbols, (str, bytes)):
        raise TypeError("symbols must be a sequence of symbol strings")
    normalized: list[str] = []
    for symbol in symbols:
        if type(symbol) is not str or not symbol or symbol.strip() != symbol:
            raise ValueError("symbols must be non-empty, already-trimmed strings")
        normalized.append(symbol)
    if len(normalized) != len(set(normalized)):
        raise ValueError("symbol scope contains duplicates")
    ordered = tuple(sorted(normalized))
    if not ordered:
        raise ValueError("symbol scope is empty")
    if len(ordered) > MAX_TOTAL_SYMBOLS:
        raise ValueError("current-observed cohort exceeds the 50-symbol bound")
    return tuple(
        ordered[offset : offset + MAX_SYMBOLS_PER_BATCH]
        for offset in range(0, len(ordered), MAX_SYMBOLS_PER_BATCH)
    )


def compose_current_observed_feature_snapshot_v2(
    *,
    batch_snapshots: Sequence[Mapping[str, Any]],
    full_cohort: Mapping[str, Any],
    snapshot_source_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Compose verified v1 child snapshots into one complete scheduled v2 snapshot.

    This accepts only a scheduled cohort whose saved recommendation artifact and
    invocation binding have already been verified by the caller. Explicit-symbol
    research scopes cannot be represented as a scheduled snapshot cohort.
    """

    eligible_symbols = _validate_full_cohort(full_cohort, snapshot_source_binding)
    chunks = partition_current_observed_symbols(eligible_symbols)
    if len(eligible_symbols) <= MAX_SYMBOLS_PER_BATCH:
        raise ValueError("v1 remains the only supported schema for scopes up to 16 symbols")
    if not 2 <= len(chunks) <= 4:
        raise ValueError("current-observed composition requires two to four batches")
    if len(batch_snapshots) != len(chunks):
        raise ValueError("feature batch count does not cover the verified cohort")

    checked_children: list[dict[str, Any]] = []
    for ordinal, (child, chunk) in enumerate(zip(batch_snapshots, chunks, strict=True)):
        checked_children.append(_validate_child_snapshot(child, chunk, ordinal))

    first = checked_children[0]
    if snapshot_source_binding.get("data_as_of_date") != first.get("cycle_source_date"):
        raise ValueError(
            "scheduled snapshot market data date differs from the G6 cycle source date"
        )
    for child in checked_children[1:]:
        for field_name in _V1_COMMON_FIELDS:
            if child[field_name] != first[field_name]:
                raise ValueError(f"feature batches have mixed current-run identity: {field_name}")

    all_rows: list[dict[str, Any]] = []
    descriptors: list[dict[str, Any]] = []
    for ordinal, child in enumerate(checked_children):
        child_symbols = tuple(str(value) for value in child["symbols"])
        child_rows = [dict(row) for row in child["rows"]]
        all_rows.extend(child_rows)
        descriptor_body: dict[str, Any] = {
            "schema_version": FEATURE_BATCH_V1,
            "ordinal": ordinal,
            "symbols": list(child_symbols),
            "row_count": len(child_rows),
            "rows_sha256": canonical_sha256({"rows": child_rows}),
            "child_snapshot_content_sha256": child["content_sha256"],
            "source_rows_sha256_by_table": dict(child["source_rows_sha256_by_table"]),
            "entry_observation": dict(child["entry_observation"]),
        }
        descriptor = dict(descriptor_body)
        descriptor["batch_sha256"] = canonical_sha256(descriptor_body)
        descriptors.append(descriptor)

    if tuple(str(row["symbol"]) for row in all_rows) != eligible_symbols:
        raise ValueError("composed feature rows do not uniquely cover the full cohort")
    rows_sha256 = canonical_sha256({"rows": all_rows})
    entry_observation = _compose_entry_observation(
        descriptors,
        symbols=eligible_symbols,
        first_child=first,
    )

    parent: dict[str, Any] = {field_name: first[field_name] for field_name in _V1_COMMON_FIELDS}
    parent.update(
        {
            "schema_version": FEATURE_SNAPSHOT_V2,
            "scope_mode": _SCHEDULED_SCOPE_MODE,
            "symbols": list(eligible_symbols),
            "rows": all_rows,
            "row_count": len(all_rows),
            "rows_sha256": rows_sha256,
            "entry_observation": entry_observation,
            "cohort_hash": str(full_cohort["cohort_hash"]),
        }
    )
    composition_body = _composition_body(
        parent,
        full_cohort=full_cohort,
        source_binding=snapshot_source_binding,
        batches=descriptors,
    )
    composition_sha256 = canonical_sha256(composition_body)
    batch_composition = {
        **composition_body,
        "composition_sha256": composition_sha256,
    }
    parent["batch_composition"] = batch_composition
    parent["composition_sha256"] = composition_sha256
    parent["content_sha256"] = canonical_sha256(parent)
    verify_current_observed_feature_snapshot_v2(parent)
    return parent


def verify_current_observed_feature_snapshot_v2(
    snapshot: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Revalidate v2 self-hashes, complete cohort, batches, rows, and entry pins."""

    if not isinstance(snapshot, Mapping):
        raise ValueError("current-observed v2 feature snapshot must be a mapping")
    if snapshot.get("schema_version") != FEATURE_SNAPSHOT_V2:
        raise ValueError("current-observed feature snapshot v2 schema is invalid")
    if (
        snapshot.get("status") != "captured"
        or snapshot.get("scope_mode") != _SCHEDULED_SCOPE_MODE
        or snapshot.get("verified") is not True
        or snapshot.get("current_restated") is not True
        or snapshot.get("historical_pit_eligible") is not False
        or snapshot.get("formal_training_allowed") is not False
        or snapshot.get("research_only") is not True
    ):
        raise ValueError("current-observed v2 feature snapshot flags are invalid")
    if "source_rows_sha256_by_table" in snapshot:
        raise ValueError("v2 parent cannot claim one global source-table hash")
    expected_keys = frozenset(
        {
            *_V1_COMMON_FIELDS,
            "schema_version",
            "scope_mode",
            "symbols",
            "rows",
            "row_count",
            "rows_sha256",
            "entry_observation",
            "cohort_hash",
            "batch_composition",
            "composition_sha256",
            "content_sha256",
        }
    )
    if set(snapshot) != expected_keys:
        raise ValueError("current-observed v2 feature snapshot fields are incomplete or unexpected")
    _require_sha256(snapshot.get("content_sha256"), "feature snapshot content_sha256")
    if canonical_sha256({key: value for key, value in snapshot.items() if key != "content_sha256"}) != snapshot.get("content_sha256"):
        raise ValueError("current-observed v2 feature snapshot content hash mismatch")

    symbols = _normalize_exact_symbols(snapshot.get("symbols"))
    if not 17 <= len(symbols) <= MAX_TOTAL_SYMBOLS:
        raise ValueError("current-observed v2 feature scope must contain 17 through 50 symbols")
    chunks = partition_current_observed_symbols(symbols)
    rows = snapshot.get("rows")
    if not isinstance(rows, list) or len(rows) != len(symbols) or snapshot.get("row_count") != len(rows):
        raise ValueError("current-observed v2 feature row coverage is incomplete")
    if tuple(_row_symbol(row) for row in rows) != symbols:
        raise ValueError("current-observed v2 feature rows are not sorted and unique")
    _validate_feature_rows(rows, symbols=symbols, snapshot=snapshot)
    rows_sha256 = canonical_sha256({"rows": rows})
    if snapshot.get("rows_sha256") != rows_sha256:
        raise ValueError("current-observed v2 full rows hash mismatch")

    composition = snapshot.get("batch_composition")
    if not isinstance(composition, Mapping) or set(composition) != _COMPOSITION_FIELDS:
        raise ValueError("current-observed v2 batch composition fields are invalid")
    if (
        composition.get("schema_version") != FEATURE_COMPOSITION_V1
        or composition.get("scope_mode") != "verified_scheduled_snapshot_cohort"
        or composition.get("max_symbols_per_batch") != MAX_SYMBOLS_PER_BATCH
        or composition.get("max_total_symbols") != MAX_TOTAL_SYMBOLS
        or composition.get("symbols") != list(symbols)
        or composition.get("rows_sha256") != rows_sha256
        or composition.get("batch_count") != len(chunks)
        or snapshot.get("composition_sha256") != composition.get("composition_sha256")
    ):
        raise ValueError("current-observed v2 composition identity differs from its parent")
    _require_sha256(composition.get("composition_sha256"), "composition_sha256")
    composition_body = {key: value for key, value in composition.items() if key != "composition_sha256"}
    if canonical_sha256(composition_body) != composition.get("composition_sha256"):
        raise ValueError("current-observed v2 composition hash mismatch")
    cohort = composition.get("full_cohort")
    source_binding = composition.get("snapshot_source_binding")
    if not isinstance(cohort, Mapping) or not isinstance(source_binding, Mapping):
        raise ValueError("current-observed v2 requires saved scheduled cohort and source binding")
    cohort_hash = _validate_full_cohort(cohort, source_binding)
    if (
        cohort_hash != symbols
        or snapshot.get("cohort_hash") != cohort.get("cohort_hash")
        or composition.get("cohort_hash") != cohort.get("cohort_hash")
        or source_binding.get("cohort_hash") != cohort.get("cohort_hash")
    ):
        raise ValueError("current-observed v2 full cohort identity mismatch")
    if (
        source_binding.get("decision_date") != snapshot.get("decision_date")
        or source_binding.get("data_as_of_date") != snapshot.get("cycle_source_date")
    ):
        raise ValueError("current-observed v2 market/source dates differ from saved cohort binding")
    verify_scheduled_snapshot_source_binding_artifacts(
        source_binding,
        full_cohort=cohort,
    )
    for field_name in (
        "cycle_id",
        "raw_run_id",
        "cycle_source_date",
        "decision_date",
        "feature_as_of_date",
        "observed_at",
        "cycle_terminal_path",
        "cycle_terminal_sha256",
        "snapshot_database_path",
        "snapshot_database_sha256",
        "snapshot_receipt_path",
        "snapshot_receipt_sha256",
        "source_context_envelope_path",
        "source_context_envelope_sha256",
        "feature_registry_id",
        "feature_registry_hash",
        "feature_schema_hash",
    ):
        if composition.get(field_name) != snapshot.get(field_name):
            raise ValueError(f"current-observed v2 composition parent pin mismatch: {field_name}")

    batches = composition.get("batches")
    if not isinstance(batches, list) or len(batches) != len(chunks):
        raise ValueError("current-observed v2 batch descriptors are incomplete")
    rows_by_symbol = {str(row["symbol"]): row for row in rows}
    checked_descriptors: list[Mapping[str, Any]] = []
    for ordinal, (descriptor, chunk) in enumerate(zip(batches, chunks, strict=True)):
        if not isinstance(descriptor, Mapping) or set(descriptor) != _BATCH_FIELDS:
            raise ValueError("current-observed v2 batch descriptor fields are invalid")
        if (
            descriptor.get("schema_version") != FEATURE_BATCH_V1
            or descriptor.get("ordinal") != ordinal
            or descriptor.get("symbols") != list(chunk)
            or descriptor.get("row_count") != len(chunk)
        ):
            raise ValueError("current-observed v2 batch symbol/ordinal identity mismatch")
        _require_sha256(descriptor.get("child_snapshot_content_sha256"), "child snapshot content hash")
        source_hashes = _validate_source_table_hashes(descriptor.get("source_rows_sha256_by_table"))
        entry = descriptor.get("entry_observation")
        if not isinstance(entry, Mapping):
            raise ValueError("current-observed v2 batch entry observation is missing")
        batch_rows = [rows_by_symbol[symbol] for symbol in chunk]
        batch_rows_sha = canonical_sha256({"rows": batch_rows})
        if descriptor.get("rows_sha256") != batch_rows_sha:
            raise ValueError("current-observed v2 batch rows hash mismatch")
        batch_body = {key: value for key, value in descriptor.items() if key != "batch_sha256"}
        _require_sha256(descriptor.get("batch_sha256"), "batch_sha256")
        if canonical_sha256(batch_body) != descriptor.get("batch_sha256"):
            raise ValueError("current-observed v2 batch hash mismatch")
        child_body = _reconstruct_child_body(
            snapshot,
            symbols=chunk,
            rows=batch_rows,
            rows_sha256=batch_rows_sha,
            source_rows_sha256_by_table=source_hashes,
            entry_observation=entry,
        )
        if canonical_sha256(child_body) != descriptor.get("child_snapshot_content_sha256"):
            raise ValueError("current-observed v2 child snapshot content hash mismatch")
        checked_descriptors.append(descriptor)
    expected_entry = _compose_entry_observation(
        checked_descriptors,
        symbols=symbols,
        first_child=_reconstruct_child_mapping(snapshot, checked_descriptors[0], rows_by_symbol),
    )
    if dict(snapshot.get("entry_observation", {})) != expected_entry:
        raise ValueError("current-observed v2 parent entry observation differs from its batches")
    return snapshot


def _validate_child_snapshot(
    snapshot: Mapping[str, Any],
    symbols: tuple[str, ...],
    ordinal: int,
) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping) or set(snapshot) != _V1_FIELDS:
        raise ValueError("a child feature snapshot has unsupported v1 fields")
    if (
        snapshot.get("schema_version") != FEATURE_SNAPSHOT_V1
        or snapshot.get("status") != "captured"
        or snapshot.get("verified") is not True
        or snapshot.get("current_restated") is not True
        or snapshot.get("historical_pit_eligible") is not False
        or snapshot.get("formal_training_allowed") is not False
        or snapshot.get("research_only") is not True
    ):
        raise ValueError(f"feature batch {ordinal} is not a captured current-only v1 snapshot")
    child_symbols = _normalize_exact_symbols(snapshot.get("symbols"))
    if child_symbols != symbols:
        raise ValueError(f"feature batch {ordinal} differs from its deterministic symbol partition")
    rows = snapshot.get("rows")
    if not isinstance(rows, list) or len(rows) != len(symbols) or snapshot.get("row_count") != len(rows):
        raise ValueError(f"feature batch {ordinal} has incomplete rows")
    if tuple(_row_symbol(row) for row in rows) != symbols:
        raise ValueError(f"feature batch {ordinal} rows are not sorted and unique")
    _validate_feature_rows(rows, symbols=symbols, snapshot=snapshot)
    if snapshot.get("rows_sha256") != canonical_sha256({"rows": rows}):
        raise ValueError(f"feature batch {ordinal} rows hash mismatch")
    _validate_source_table_hashes(snapshot.get("source_rows_sha256_by_table"))
    if not _verified_content_hash(snapshot, "content_sha256"):
        raise ValueError(f"feature batch {ordinal} content hash mismatch")
    entry = snapshot.get("entry_observation")
    if not isinstance(entry, Mapping):
        raise ValueError(f"feature batch {ordinal} entry observation is missing")
    _validate_entry_identity(entry, snapshot)
    return dict(snapshot)


def _validate_full_cohort(
    full_cohort: Mapping[str, Any],
    snapshot_source_binding: Mapping[str, Any],
) -> tuple[str, ...]:
    if not isinstance(full_cohort, Mapping) or not isinstance(snapshot_source_binding, Mapping):
        raise ValueError("verified scheduled cohort and source binding are required")
    if full_cohort.get("schema_version") != SCHEDULED_COHORT_V1:
        raise ValueError("scheduled snapshot cohort schema is unsupported")
    cohort_hash = full_cohort.get("cohort_hash")
    _require_sha256(cohort_hash, "scheduled cohort hash")
    cohort_body = {key: value for key, value in full_cohort.items() if key != "cohort_hash"}
    if canonical_sha256(cohort_body) != cohort_hash:
        raise ValueError("scheduled snapshot cohort hash does not match its complete body")
    symbols = _normalize_exact_symbols(full_cohort.get("eligible_symbols"))
    if not 17 <= len(symbols) <= MAX_TOTAL_SYMBOLS:
        raise ValueError("verified scheduled cohort must contain 17 through 50 eligible symbols")
    if full_cohort.get("eligible_symbols") != list(symbols):
        raise ValueError("scheduled cohort eligible symbols must be sorted and unique")
    if full_cohort.get("eligible_count") != len(symbols):
        raise ValueError("scheduled cohort eligible count does not match its symbols")

    required_fields = (
        "snapshot_output_root",
        "result_id",
        "schema_version",
        "schema_revision",
        "integrity_basis",
        "raw_artifact_sha256",
        "payload_hash",
        "cohort_hash",
        "invocation_output_path",
        "invocation_output_size",
        "invocation_output_sha256",
        "decision_date",
        "data_as_of_date",
        "decision_at",
        "available_at",
    )
    if any(field not in snapshot_source_binding for field in required_fields):
        raise ValueError("verified scheduled snapshot source binding is incomplete")
    schema_revision = snapshot_source_binding.get("schema_revision")
    invocation_output_size = snapshot_source_binding.get("invocation_output_size")
    if type(schema_revision) is not int or type(invocation_output_size) is not int:
        raise ValueError("scheduled snapshot source binding numeric identity is invalid")
    if (
        type(snapshot_source_binding.get("result_id")) is not str
        or not snapshot_source_binding["result_id"].strip()
        or snapshot_source_binding.get("integrity_basis") != "canonical_payload_and_index_verified"
        or snapshot_source_binding.get("cohort_hash") != cohort_hash
        or type(snapshot_source_binding.get("schema_version")) is not str
        or not snapshot_source_binding.get("schema_version")
        or schema_revision <= 0
        or invocation_output_size <= 0
    ):
        raise ValueError("scheduled snapshot source binding identity is invalid")
    for field in ("raw_artifact_sha256", "payload_hash", "invocation_output_sha256"):
        _require_sha256(snapshot_source_binding.get(field), field)
    invocation_path = snapshot_source_binding.get("invocation_output_path")
    if type(invocation_path) is not str or not invocation_path or not _is_absolute_path(invocation_path):
        raise ValueError("scheduled snapshot invocation output path must be absolute")
    snapshot_output_root = snapshot_source_binding.get("snapshot_output_root")
    if (
        type(snapshot_output_root) is not str
        or not snapshot_output_root
        or not _is_absolute_path(snapshot_output_root)
    ):
        raise ValueError("scheduled snapshot output root must be absolute")
    for field in ("decision_date", "data_as_of_date"):
        _require_iso_date(snapshot_source_binding.get(field), field)
    if snapshot_source_binding.get("decision_date") != full_cohort.get("decision_date", snapshot_source_binding.get("decision_date")):
        raise ValueError("scheduled cohort decision date differs from its source binding")
    _require_aware_datetime(snapshot_source_binding.get("decision_at"), "decision_at")
    if snapshot_source_binding.get("available_at") is not None:
        _require_aware_datetime(snapshot_source_binding.get("available_at"), "available_at")
    return symbols


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

    _validate_full_cohort(full_cohort, snapshot_source_binding)
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


def _validate_feature_rows(
    rows: Sequence[Any],
    *,
    symbols: tuple[str, ...],
    snapshot: Mapping[str, Any],
) -> None:
    expected_features = None
    decision = snapshot.get("decision_date")
    feature_as_of = snapshot.get("feature_as_of_date")
    observed_at = snapshot.get("observed_at")
    _require_iso_date(decision, "decision_date")
    _require_iso_date(feature_as_of, "feature_as_of_date")
    feature_day = datetime.strptime(str(feature_as_of), "%Y-%m-%d").date()
    decision_day = datetime.strptime(str(decision), "%Y-%m-%d").date()
    if feature_day >= decision_day:
        raise ValueError("feature-as-of date must precede decision date")
    _require_aware_datetime(observed_at, "observed_at")
    for expected_symbol, raw_row in zip(symbols, rows, strict=True):
        if not isinstance(raw_row, Mapping):
            raise ValueError("feature snapshot row is not an object")
        if (
            raw_row.get("symbol") != expected_symbol
            or raw_row.get("decision_date") != decision
            or raw_row.get("feature_as_of_date") != feature_as_of
            or raw_row.get("feature_available_date") != decision
            or raw_row.get("local_current_observed_at") != observed_at
            or raw_row.get("historical_pit_eligible") is not False
            or raw_row.get("formal_training_allowed") is not False
        ):
            raise ValueError("feature row dates, scope, or eligibility flags differ from parent")
        feature_ids = raw_row.get("feature_ids")
        feature_values = raw_row.get("feature_values")
        missing_ids = raw_row.get("missing_feature_ids")
        if (
            not isinstance(feature_ids, list)
            or len(feature_ids) != 20
            or len(set(feature_ids)) != 20
            or not isinstance(feature_values, list)
            or len(feature_values) != 20
            or any(value is not None and type(value) is not int for value in feature_values)
            or not isinstance(missing_ids, list)
            or any(type(value) is not str for value in missing_ids)
        ):
            raise ValueError("feature row must carry exactly twenty typed feature slots")
        if expected_features is None:
            expected_features = tuple(feature_ids)
        elif tuple(feature_ids) != expected_features:
            raise ValueError("feature rows have mixed feature registry slots")
        for field_name in ("feature_registry_id", "feature_registry_hash", "feature_schema_hash"):
            if raw_row.get(field_name) != snapshot.get(field_name):
                raise ValueError(f"feature row registry identity differs from parent: {field_name}")
        _require_sha256(raw_row.get("row_sha256"), "feature row hash")


def _compose_entry_observation(
    batches: Sequence[Mapping[str, Any]],
    *,
    symbols: tuple[str, ...],
    first_child: Mapping[str, Any],
) -> dict[str, Any]:
    entries = [batch.get("entry_observation") for batch in batches]
    if any(not isinstance(entry, Mapping) for entry in entries):
        raise ValueError("batch entry observation is missing")
    typed_entries = [entry for entry in entries if isinstance(entry, Mapping)]
    statuses = [entry.get("status") for entry in typed_entries]
    if any(status not in {"captured", "pending", "blocked"} for status in statuses):
        raise ValueError("batch entry observation status is invalid")
    base_entry = dict(typed_entries[0])
    for entry in typed_entries:
        _validate_entry_identity(entry, first_child)
        for field in (
            "schema_version",
            "decision_date",
            "cycle_source_date",
            "source_database_path",
            "source_database_sha256",
            "local_observed_at",
            "source_available_at",
            "historical_pit_eligible",
            "formal_training_allowed",
            "current_restated",
            "research_only",
        ):
            if entry.get(field) != base_entry.get(field):
                raise ValueError(f"batch entry observations have mixed identity: {field}")
    if all(status == "captured" for status in statuses):
        benchmark = typed_entries[0].get("benchmark_entry_price_pin")
        session_proof = typed_entries[0].get("entry_session_proof")
        scheduled_close = typed_entries[0].get("scheduled_market_close_at")
        stock_pins: dict[str, Any] = {}
        for descriptor, entry in zip(batches, typed_entries, strict=True):
            if (
                entry.get("benchmark_entry_price_pin") != benchmark
                or entry.get("entry_session_proof") != session_proof
                or entry.get("scheduled_market_close_at") != scheduled_close
                or entry.get("missing_symbols") != []
            ):
                raise ValueError("captured batch entry proofs have inconsistent benchmark/session identity")
            pins = entry.get("entry_price_pin_by_symbol")
            batch_symbols = descriptor.get("symbols")
            if (
                not isinstance(pins, Mapping)
                or not isinstance(batch_symbols, list)
                or set(pins) != set(batch_symbols)
            ):
                raise ValueError("captured batch entry pins do not cover its exact symbol slice")
            overlap = set(stock_pins).intersection(pins)
            if overlap:
                raise ValueError("captured batch entry pins duplicate symbols")
            stock_pins.update(dict(pins))
        if set(stock_pins) != set(symbols):
            raise ValueError("captured batch entry pins do not cover the complete cohort")
        result = dict(base_entry)
        result["status"] = "captured"
        result["entry_price_pin_by_symbol"] = stock_pins
        result["benchmark_entry_price_pin"] = benchmark
        result["entry_session_proof"] = session_proof
        result["scheduled_market_close_at"] = scheduled_close
        result["missing_symbols"] = []
        return result

    status = "blocked" if "blocked" in statuses else "pending"
    diagnostic_rows: list[dict[str, Any]] = []
    missing: set[str] = set()
    for descriptor, entry in zip(batches, typed_entries, strict=True):
        batch_symbols = descriptor.get("symbols")
        missing_values = entry.get("missing_symbols")
        if isinstance(missing_values, list):
            missing.update(str(symbol) for symbol in missing_values)
        if entry.get("status") != "captured" and not missing_values and isinstance(batch_symbols, list):
            missing.update(str(symbol) for symbol in batch_symbols)
        diagnostic_rows.append(
            {
                "ordinal": descriptor.get("ordinal"),
                "status": entry.get("status"),
                "reason": entry.get("reason"),
                "missing_symbols": list(missing_values) if isinstance(missing_values, list) else [],
            }
        )
    result = dict(base_entry)
    result.update(
        {
            "status": status,
            "reason": "current_observed_batch_entry_not_ready",
            "missing_symbols": sorted(missing),
            "entry_price_pin_by_symbol": {},
            "benchmark_entry_price_pin": None,
            "batch_diagnostics": diagnostic_rows,
        }
    )
    # A shared session proof may still be useful diagnostic context, but it is
    # never promoted to an entry pin while any batch is pending or blocked.
    proof_values = [entry.get("entry_session_proof") for entry in typed_entries]
    if proof_values and all(value == proof_values[0] for value in proof_values) and proof_values[0] is not None:
        result["entry_session_proof"] = proof_values[0]
        result["scheduled_market_close_at"] = typed_entries[0].get("scheduled_market_close_at")
    else:
        result.pop("entry_session_proof", None)
        result.pop("scheduled_market_close_at", None)
    return result


def _validate_entry_identity(entry: Mapping[str, Any], snapshot: Mapping[str, Any]) -> None:
    if (
        entry.get("schema_version") != ENTRY_OBSERVATION_V1
        or entry.get("decision_date") != snapshot.get("decision_date")
        or entry.get("cycle_source_date") != snapshot.get("cycle_source_date")
        or entry.get("source_database_path") != snapshot.get("snapshot_database_path")
        or entry.get("source_database_sha256") != snapshot.get("snapshot_database_sha256")
        or entry.get("current_restated") is not True
        or entry.get("research_only") is not True
        or entry.get("historical_pit_eligible") is not False
        or entry.get("formal_training_allowed") is not False
        or entry.get("source_available_at") is not None
    ):
        raise ValueError("batch entry observation identity or research-only flags are invalid")
    _require_aware_datetime(entry.get("local_observed_at"), "entry local_observed_at")


def _validate_source_table_hashes(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != set(SOURCE_TABLES):
        raise ValueError("each batch must carry the exact four source-table hashes")
    normalized: dict[str, str] = {}
    for table in SOURCE_TABLES:
        digest = value.get(table)
        _require_sha256(digest, f"source table hash {table}")
        normalized[table] = str(digest)
    return normalized


def _composition_body(
    parent: Mapping[str, Any],
    *,
    full_cohort: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    batches: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": FEATURE_COMPOSITION_V1,
        "scope_mode": _SCHEDULED_SCOPE_MODE,
        "cohort_hash": str(full_cohort.get("cohort_hash") or ""),
        "full_cohort": dict(full_cohort),
        "snapshot_source_binding": dict(source_binding),
        "max_symbols_per_batch": MAX_SYMBOLS_PER_BATCH,
        "max_total_symbols": MAX_TOTAL_SYMBOLS,
        "batch_count": len(batches),
        "batches": [dict(batch) for batch in batches],
        "symbols": list(parent["symbols"]),
        "rows_sha256": str(parent["rows_sha256"]),
    }
    for field_name in (
        "cycle_id",
        "raw_run_id",
        "cycle_source_date",
        "decision_date",
        "feature_as_of_date",
        "observed_at",
        "cycle_terminal_path",
        "cycle_terminal_sha256",
        "snapshot_database_path",
        "snapshot_database_sha256",
        "snapshot_receipt_path",
        "snapshot_receipt_sha256",
        "source_context_envelope_path",
        "source_context_envelope_sha256",
        "feature_registry_id",
        "feature_registry_hash",
        "feature_schema_hash",
    ):
        body[field_name] = parent[field_name]
    return body


def _reconstruct_child_mapping(
    parent: Mapping[str, Any],
    descriptor: Mapping[str, Any],
    rows_by_symbol: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    batch_symbols = tuple(str(value) for value in descriptor["symbols"])
    rows = [dict(rows_by_symbol[symbol]) for symbol in batch_symbols]
    body = _reconstruct_child_body(
        parent,
        symbols=batch_symbols,
        rows=rows,
        rows_sha256=str(descriptor["rows_sha256"]),
        source_rows_sha256_by_table=dict(descriptor["source_rows_sha256_by_table"]),
        entry_observation=dict(descriptor["entry_observation"]),
    )
    body["content_sha256"] = canonical_sha256(body)
    return body


def _reconstruct_child_body(
    parent: Mapping[str, Any],
    *,
    symbols: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    rows_sha256: str,
    source_rows_sha256_by_table: Mapping[str, str],
    entry_observation: Mapping[str, Any],
) -> dict[str, Any]:
    body = {field_name: parent[field_name] for field_name in _V1_COMMON_FIELDS}
    body.update(
        {
            "schema_version": FEATURE_SNAPSHOT_V1,
            "symbols": list(symbols),
            "rows": [dict(row) for row in rows],
            "row_count": len(rows),
            "rows_sha256": rows_sha256,
            "source_rows_sha256_by_table": dict(source_rows_sha256_by_table),
            "entry_observation": dict(entry_observation),
        }
    )
    return body


def _row_symbol(row: object) -> str:
    if not isinstance(row, Mapping) or type(row.get("symbol")) is not str or not row["symbol"]:
        raise ValueError("feature snapshot row has no valid symbol")
    return str(row["symbol"])


def _normalize_exact_symbols(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("symbol list is missing")
    symbols = tuple(value)
    if any(type(symbol) is not str or not symbol or symbol.strip() != symbol for symbol in symbols):
        raise ValueError("symbols must be non-empty, trimmed strings")
    if symbols != tuple(sorted(symbols)) or len(symbols) != len(set(symbols)):
        raise ValueError("symbols must be sorted and unique")
    return symbols


def _verified_content_hash(payload: Mapping[str, Any], field: str) -> bool:
    declared = payload.get(field)
    return (
        _is_sha256(declared)
        and canonical_sha256({key: value for key, value in payload.items() if key != field}) == declared
    )


def _require_sha256(value: object, label: str) -> None:
    if not _is_sha256(value):
        raise ValueError(f"{label} is not a prefixed lowercase SHA-256 digest")


def _is_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(char in "0123456789abcdef" for char in value[7:])
    )


def _require_iso_date(value: object, label: str) -> None:
    if type(value) is not str or len(value) != 10:
        raise ValueError(f"{label} must be an ISO YYYY-MM-DD date")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO YYYY-MM-DD date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must be an ISO YYYY-MM-DD date")


def _require_aware_datetime(value: object, label: str) -> None:
    if type(value) is not str:
        raise ValueError(f"{label} must be an aware ISO datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an aware ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be an aware ISO datetime")


def _is_absolute_path(value: str) -> bool:
    from pathlib import PurePath
    from pathlib import PureWindowsPath

    return PurePath(value).is_absolute() or PureWindowsPath(value).is_absolute()
