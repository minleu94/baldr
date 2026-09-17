"""Immutable provenance contracts for recommendation inference projections.

This module is intentionally independent from the application consumer.  It
hashes the bounded raw snapshot and the exact feature rows consumed for one
decision date, validates the shared feature transform contract, and persists a
create-only projection receipt.  Training hashes and next-day inference hashes
are separate identities; a training dataset hash is never compared with an
inference snapshot hash.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence, cast

from ml_module.recommendation_probability_transform import PROBABILITY_TRANSFORM_ID


INFERENCE_PROVENANCE_SCHEMA_VERSION = "recommendation-inference-provenance.v1"
PROJECTION_RECEIPT_SCHEMA_VERSION = "recommendation-calibration-projection-receipt.v1"
PROVENANCE_COMPATIBILITY_SCHEMA_VERSION = (
    "recommendation-calibration-provenance-compatibility.v1"
)
FEATURE_TRANSFORM_CONTRACT_ID = "historical-feature-builder.core-long-history.v1"
FEATURE_DECISION_TIMING = "decision_t_uses_previous_trading_day"
FEATURE_MISSING_POLICY = "missing_is_not_zero"
PROJECTION_SELECTION_AUTHORITY = "rule_top_n"
PROJECTION_SELECTION_SCORE_KIND = "rule_total_score"
PROJECTION_SELECTION_PERCENTILE_KIND = "rule_percentile"
PROJECTION_MODEL_RANKING_KIND = "model_return_bp"


class RecommendationProvenanceError(ValueError):
    """Raised when inference or projection provenance cannot be verified."""


def build_feature_transform_contract(
    *,
    feature_registry_hash: str | None,
    feature_schema: Sequence[Sequence[str]],
    feature_builder_schema_hash: str | None = None,
) -> dict[str, Any]:
    """Return the canonical transform identity shared by training and inference."""

    canonical_schema = _canonical_feature_schema(feature_schema)
    schema_hash = _feature_schema_hash(canonical_schema)
    payload: dict[str, Any] = {
        "contract_id": FEATURE_TRANSFORM_CONTRACT_ID,
        "feature_registry_hash": _optional_hash(feature_registry_hash),
        "feature_schema_hash": schema_hash,
        "canonical_schema": [list(item) for item in canonical_schema],
        "decision_timing": FEATURE_DECISION_TIMING,
        "missing_policy": FEATURE_MISSING_POLICY,
        "shadow_only": True,
        "production_action_allowed": False,
    }
    payload["contract_hash"] = _hash_payload(payload)
    # The builder implementation hash is useful for raw-source audit, but is
    # intentionally not part of shared model/schema compatibility: training
    # and inference can be produced by equivalent builder versions.
    payload["feature_builder_schema_hash"] = _optional_hash(feature_builder_schema_hash)
    return payload


def verify_feature_transform_contract(
    contract: Mapping[str, Any],
    *,
    expected_registry_hash: str | None = None,
    expected_schema: Sequence[Sequence[str]] | None = None,
) -> None:
    """Verify a transform contract without permitting a production flag."""

    if not isinstance(contract, Mapping):
        raise RecommendationProvenanceError("feature transform contract is missing")
    body = {
        key: value
        for key, value in contract.items()
        if key not in {"contract_hash", "feature_builder_schema_hash"}
    }
    if contract.get("contract_hash") != _hash_payload(body):
        raise RecommendationProvenanceError("feature transform contract hash mismatch")
    if contract.get("contract_id") != FEATURE_TRANSFORM_CONTRACT_ID:
        raise RecommendationProvenanceError("feature transform contract id is unsupported")
    if contract.get("decision_timing") != FEATURE_DECISION_TIMING:
        raise RecommendationProvenanceError("feature transform decision timing is invalid")
    if contract.get("missing_policy") != FEATURE_MISSING_POLICY:
        raise RecommendationProvenanceError("feature transform missing policy is invalid")
    if contract.get("shadow_only") is not True:
        raise RecommendationProvenanceError("feature transform contract is not shadow-only")
    if contract.get("production_action_allowed") is not False:
        raise RecommendationProvenanceError("feature transform production flag is invalid")
    registry_hash = contract.get("feature_registry_hash")
    if registry_hash is not None:
        _require_hash(str(registry_hash), "feature transform registry hash")
    if expected_registry_hash is not None and registry_hash != expected_registry_hash:
        raise RecommendationProvenanceError("feature transform registry hash mismatch")
    schema = contract.get("canonical_schema")
    canonical_schema = _canonical_feature_schema(schema if isinstance(schema, Sequence) else ())
    if expected_schema is not None and canonical_schema != _canonical_feature_schema(expected_schema):
        raise RecommendationProvenanceError("feature transform canonical schema mismatch")
    if contract.get("feature_schema_hash") != _feature_schema_hash(canonical_schema):
        raise RecommendationProvenanceError("feature transform feature schema hash mismatch")
    builder_hash = contract.get("feature_builder_schema_hash")
    if builder_hash is not None:
        _require_hash(str(builder_hash), "feature builder schema hash")


def training_source_hash_from_payload(payload: Mapping[str, Any]) -> str:
    """Hash the source identity that produced the merged training dataset."""

    return _hash_payload(
        {
            "dataset_hash": payload.get("dataset_hash"),
            "merged_samples_payload_hash": payload.get("merged_samples_payload_hash"),
            "source_contract": payload.get("source_contract"),
            "source_groups": payload.get("source_groups"),
            "source_role_row_ids": payload.get("source_role_row_ids"),
            "deduplication": payload.get("deduplication"),
            "replay_manifests": payload.get("replay_manifests"),
            "natural_sample_ids": payload.get("natural_sample_ids"),
        }
    )


def training_pit_hash_from_payload(payload: Mapping[str, Any]) -> str:
    """Hash the complete training cutoff/PIT assertion map."""

    return _hash_payload(payload.get("pit"))


def build_training_provenance(
    *,
    lineage_payload: Mapping[str, Any] | None,
    manifest_hash: str | None = None,
    manifest_path: str | None = None,
    candidate_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize a verified lineage manifest for a projection receipt.

    A missing or pre-P1 lineage is deliberately returned as
    ``legacy_unproven``.  It is never upgraded by inference metadata.
    """

    if lineage_payload is None:
        return {
            "schema_version": INFERENCE_PROVENANCE_SCHEMA_VERSION,
            "status": "legacy_unproven",
            "reason": "training_lineage_not_declared",
            "manifest_hash": manifest_hash,
            "manifest_path": manifest_path,
            "training_source_hash": None,
            "training_pit_hash": None,
            "feature_registry_hash": None,
            "feature_schema_hash": None,
            "feature_transform_contract": None,
            "feature_transform_contract_hash": None,
            "dataset_id": None,
            "dataset_hash": None,
            "label_registry_hash": None,
            "label_contract_id": None,
            "return_basis": None,
            "decision_date": None,
            "training_as_of": None,
            "training_semantics": None,
            "decision_time_eligible": None,
            "research_only": None,
            "cost_scenario_hash": None,
        }

    payload = _json_mapping(lineage_payload)
    source_declared = "training_source_hash" in payload
    pit_declared = "training_pit_hash" in payload
    if source_declared != pit_declared:
        raise RecommendationProvenanceError(
            "training source and PIT hashes must be declared together"
        )
    declared_source_hash = str(payload.get("training_source_hash") or "")
    declared_pit_hash = str(payload.get("training_pit_hash") or "")
    if source_declared and (not declared_source_hash or not declared_pit_hash):
        raise RecommendationProvenanceError(
            "training source and PIT hashes must both be non-empty"
        )
    has_p1_hashes = bool(declared_source_hash and declared_pit_hash)
    if has_p1_hashes:
        _require_hash(declared_source_hash, "training_source_hash")
        _require_hash(declared_pit_hash, "training_pit_hash")
        if declared_source_hash != training_source_hash_from_payload(payload):
            raise RecommendationProvenanceError("training source hash mismatch")
        if declared_pit_hash != training_pit_hash_from_payload(payload):
            raise RecommendationProvenanceError("training PIT hash mismatch")

    transform_declared = "feature_transform_contract" in payload
    transform = payload.get("feature_transform_contract")
    if transform_declared and not isinstance(transform, Mapping):
        raise RecommendationProvenanceError(
            "training feature transform contract is invalid"
        )
    if isinstance(transform, Mapping):
        verify_feature_transform_contract(transform)
    if transform_declared != has_p1_hashes:
        raise RecommendationProvenanceError(
            "training P1 provenance declarations are incomplete"
        )
    status = "verified" if has_p1_hashes else "legacy_unproven"
    reason = None if has_p1_hashes else "training_lineage_pre_p1_hashes_missing"

    candidate = candidate_payload if isinstance(candidate_payload, Mapping) else {}
    lineage_label_hash = str(payload.get("label_registry_hash") or "").strip()
    candidate_label_hash = str(candidate.get("label_registry_hash") or "").strip()
    if lineage_label_hash and candidate_label_hash and lineage_label_hash != candidate_label_hash:
        raise RecommendationProvenanceError(
            "candidate label registry hash does not match training lineage"
        )
    label_registry_hash = lineage_label_hash or candidate_label_hash or None
    if label_registry_hash is not None:
        _require_hash(label_registry_hash, "training label registry hash")
    lineage_label_contract = str(payload.get("label_contract_id") or "").strip()
    candidate_label_contract = str(candidate.get("label_contract_id") or "").strip()
    if (
        lineage_label_contract
        and candidate_label_contract
        and lineage_label_contract != candidate_label_contract
    ):
        raise RecommendationProvenanceError(
            "candidate label contract does not match training lineage"
        )
    label_contract_id = lineage_label_contract or candidate_label_contract or None
    lineage_return_basis = str(payload.get("return_basis") or "").strip()
    candidate_return_basis = str(candidate.get("return_basis") or "").strip()
    if (
        lineage_return_basis
        and candidate_return_basis
        and lineage_return_basis != candidate_return_basis
    ):
        raise RecommendationProvenanceError(
            "candidate return basis does not match training lineage"
        )
    return_basis = lineage_return_basis or candidate_return_basis or None
    candidate_hash_values = [
        candidate.get(key)
        for key in (
            "training_source_hash",
            "training_pit_hash",
            "feature_transform_contract_hash",
        )
    ]
    candidate_has_any_p1_hash = any(value not in (None, "") for value in candidate_hash_values)
    candidate_has_all_p1_hashes = all(value not in (None, "") for value in candidate_hash_values)
    if candidate_has_any_p1_hash and not candidate_has_all_p1_hashes:
        raise RecommendationProvenanceError(
            "candidate P1 training provenance declarations are incomplete"
        )
    for key in (
        "training_source_hash",
        "training_pit_hash",
        "feature_transform_contract_hash",
    ):
        declared = candidate.get(key)
        lineage_value = (
            payload.get("feature_transform_contract", {}).get("contract_hash")
            if key == "feature_transform_contract_hash"
            and isinstance(payload.get("feature_transform_contract"), Mapping)
            else payload.get(key)
        )
        if declared not in (None, ""):
            _require_hash(str(declared), f"candidate {key}")
        if declared not in (None, "") and declared != lineage_value:
            raise RecommendationProvenanceError(
                f"candidate {key} does not match training lineage"
            )
    candidate_transform = candidate.get("feature_transform_contract")
    if candidate_transform not in (None, ""):
        if not isinstance(candidate_transform, Mapping):
            raise RecommendationProvenanceError(
                "candidate feature transform contract is invalid"
            )
        verify_feature_transform_contract(candidate_transform)
        if not isinstance(transform, Mapping) or dict(candidate_transform) != dict(transform):
            raise RecommendationProvenanceError(
                "candidate feature transform contract does not match training lineage"
            )
    feature_registry_hash = payload.get("feature_registry_hash")
    if feature_registry_hash not in (None, ""):
        _require_hash(str(feature_registry_hash), "training feature registry hash")
    feature_schema_hash = payload.get("feature_schema_hash")
    if feature_schema_hash not in (None, ""):
        _require_hash(str(feature_schema_hash), "training feature schema hash")
    cost_hash = payload.get("cost_scenario_hash")
    if cost_hash not in (None, ""):
        _require_hash(str(cost_hash), "training cost scenario hash")
    return {
        "schema_version": INFERENCE_PROVENANCE_SCHEMA_VERSION,
        "status": status,
        "reason": reason,
        "manifest_hash": manifest_hash,
        "manifest_path": manifest_path,
        "training_source_hash": payload.get("training_source_hash"),
        "training_pit_hash": payload.get("training_pit_hash"),
        "feature_registry_hash": feature_registry_hash,
        "feature_schema_hash": feature_schema_hash,
        "feature_transform_contract": dict(transform) if transform is not None else None,
        "feature_transform_contract_hash": (
            transform.get("contract_hash") if isinstance(transform, Mapping) else None
        ),
        "dataset_id": payload.get("dataset_id"),
        "dataset_hash": payload.get("dataset_hash"),
        "label_registry_hash": label_registry_hash,
        "label_contract_id": label_contract_id,
        "return_basis": return_basis,
        "decision_date": payload.get("decision_date"),
        "training_as_of": payload.get("training_as_of"),
        "training_semantics": (
            payload.get("training_context", {}).get("semantics")
            if isinstance(payload.get("training_context"), Mapping)
            else None
        ),
        "decision_time_eligible": (
            payload.get("training_context", {}).get("decision_time_eligible")
            if isinstance(payload.get("training_context"), Mapping)
            else None
        ),
        "research_only": (
            payload.get("dataset_quality", {}).get("research_only")
            if isinstance(payload.get("dataset_quality"), Mapping)
            else None
        ),
        "cost_scenario_hash": cost_hash,
    }


def build_inference_provenance(
    *,
    snapshot: Any,
    feature_rows: Sequence[Any],
    feature_schema: Sequence[Sequence[str]],
    feature_registry_hash: str,
    feature_builder_schema_hash: str | None = None,
    source_database: str | None = None,
    history_start_date: str | None = None,
    cost_scenario_hash: str | None = None,
    cost_scenario_id: str | None = None,
    cost_scenario_version: str | None = None,
    probability_transform_id: str | None = None,
    source_contract_binding: Mapping[str, Any] | None = None,
    row_ids_by_symbol: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build provenance from the exact bounded raw snapshot and feature rows."""

    canonical_schema = _canonical_feature_schema(feature_schema)
    if not feature_registry_hash:
        raise RecommendationProvenanceError("inference feature registry hash is required")
    _require_hash(feature_registry_hash, "inference feature registry hash")
    decision_date = _date_text(_value(snapshot, "decision_date"), "snapshot.decision_date")
    feature_as_of_date = _date_text(
        _value(snapshot, "feature_as_of_date"), "snapshot.feature_as_of_date"
    )
    if date.fromisoformat(feature_as_of_date) >= date.fromisoformat(decision_date):
        raise RecommendationProvenanceError("inference feature cutoff is not before decision")
    raw_snapshot = _raw_snapshot_payload(snapshot, decision_date, feature_as_of_date)
    raw_snapshot_hash = _hash_payload(raw_snapshot)
    rows = _feature_rows_payload(
        feature_rows,
        decision_date=decision_date,
        feature_schema=canonical_schema,
        row_ids_by_symbol=row_ids_by_symbol,
    )
    if not rows:
        raise RecommendationProvenanceError("inference feature rows are empty")
    symbols = [str(row["symbol"]) for row in rows]
    if len(symbols) != len(set(symbols)):
        raise RecommendationProvenanceError("inference feature row symbols are duplicated")
    row_hash = _feature_rows_hash(
        decision_date=decision_date,
        feature_registry_hash=feature_registry_hash,
        feature_schema_hash=_feature_schema_hash(canonical_schema),
        rows=rows,
    )
    snapshot_fingerprint = _hash_payload(
        {"capture_decision_date": decision_date, "rows": rows}
    )
    pit = {
        "decision_date": decision_date,
        "feature_as_of_date": feature_as_of_date,
        "feature_as_of_before_decision": True,
        "feature_available_not_after_decision": True,
        "rows": [
            {
                "symbol": row["symbol"],
                "decision_date": row["decision_date"],
                "feature_as_of_date": row["feature_as_of_date"],
                "feature_available_date": row["feature_available_date"],
            }
            for row in rows
        ],
    }
    transform = build_feature_transform_contract(
        feature_registry_hash=feature_registry_hash,
        feature_schema=canonical_schema,
        feature_builder_schema_hash=feature_builder_schema_hash,
    )
    source_binding: dict[str, Any] | None = None
    source_contract_status = "not_supplied"
    if source_contract_binding is not None:
        verify_source_contract_binding(
            source_contract_binding,
            decision_date=decision_date,
            feature_rows=rows,
            feature_registry_hash=feature_registry_hash,
            feature_schema_hash=transform["feature_schema_hash"],
            feature_builder_schema_hash=transform["feature_builder_schema_hash"],
            source_database=source_database,
            history_start_date=history_start_date,
        )
        source_binding = _json_mapping(source_contract_binding)
        source_contract_status = "verified"
    source_identity = {
        "source_kind": type(snapshot).__name__,
        "source_fingerprint": str(_value(snapshot, "source_fingerprint") or ""),
        "raw_snapshot_content_sha256": raw_snapshot_hash,
        "feature_rows_sha256": row_hash,
        "feature_snapshot_fingerprint": snapshot_fingerprint,
        "source_tables": list(_value(snapshot, "source_tables") or ()),
        "query_count": int(_value(snapshot, "query_count") or 0),
    }
    inference_source_hash = _hash_payload(source_identity)
    inference_pit_hash = _hash_payload(pit)
    provenance: dict[str, Any] = {
        "schema_version": INFERENCE_PROVENANCE_SCHEMA_VERSION,
        "status": "verified",
        "decision_date": decision_date,
        "feature_as_of_date": feature_as_of_date,
        "symbols": symbols,
        "feature_registry_hash": feature_registry_hash,
        "feature_schema_hash": transform["feature_schema_hash"],
        "feature_builder_schema_hash": transform["feature_builder_schema_hash"],
        "feature_transform_contract": transform,
        "source_database": str(source_database or "") or None,
        "history_start_date": (
            _date_text(history_start_date, "history_start_date")
            if history_start_date
            else None
        ),
        "source_fingerprint": source_identity["source_fingerprint"],
        "source_tables": source_identity["source_tables"],
        "query_count": source_identity["query_count"],
        "raw_snapshot_content_sha256": raw_snapshot_hash,
        "feature_rows_sha256": row_hash,
        "feature_snapshot_fingerprint": snapshot_fingerprint,
        "feature_rows": rows,
        "pit": pit,
        "inference_source_hash": inference_source_hash,
        "inference_pit_hash": inference_pit_hash,
        "source_contract_status": source_contract_status,
        "source_contract_binding": source_binding,
        "cost_scenario_hash": cost_scenario_hash,
        "cost_scenario_id": cost_scenario_id,
        "cost_scenario_version": cost_scenario_version,
        "probability_transform_id": probability_transform_id,
        "raw_snapshot_contract": {
            "schema_version": INFERENCE_PROVENANCE_SCHEMA_VERSION,
            "source_kind": source_identity["source_kind"],
            "source_content_scope": "bounded_consumed_snapshot",
            "raw_snapshot_content_sha256": raw_snapshot_hash,
        },
        "source_kind": source_identity["source_kind"],
        "shadow_only": True,
        "production_action_allowed": False,
    }
    provenance["provenance_hash"] = _hash_payload(
        {key: value for key, value in provenance.items() if key != "provenance_hash"}
    )
    return provenance


def verify_inference_provenance(
    provenance: Mapping[str, Any],
    *,
    expected_decision_date: str | None = None,
    expected_symbols: Sequence[str] | None = None,
    expected_registry_hash: str | None = None,
    expected_schema: Sequence[Sequence[str]] | None = None,
    expected_probability_transform_id: str | None = None,
) -> None:
    """Recompute row/PIT/source identity from a persisted inference payload."""

    if not isinstance(provenance, Mapping):
        raise RecommendationProvenanceError("inference provenance is not an object")
    if provenance.get("schema_version") != INFERENCE_PROVENANCE_SCHEMA_VERSION:
        raise RecommendationProvenanceError("inference provenance schema is unsupported")
    if provenance.get("status") != "verified":
        raise RecommendationProvenanceError("inference provenance is not verified")
    if provenance.get("shadow_only") is not True or provenance.get("production_action_allowed") is not False:
        raise RecommendationProvenanceError("inference provenance production flags are invalid")
    decision_date = _date_text(provenance.get("decision_date"), "inference.decision_date")
    feature_as_of_date = _date_text(
        provenance.get("feature_as_of_date"), "inference.feature_as_of_date"
    )
    if date.fromisoformat(feature_as_of_date) >= date.fromisoformat(decision_date):
        raise RecommendationProvenanceError(
            "inference feature cutoff is not before decision"
        )
    if expected_decision_date is not None and decision_date != _date_text(expected_decision_date, "expected_decision_date"):
        raise RecommendationProvenanceError("inference provenance decision date mismatch")
    registry_hash = str(provenance.get("feature_registry_hash") or "")
    _require_hash(registry_hash, "inference feature registry hash")
    if expected_registry_hash is not None and registry_hash != expected_registry_hash:
        raise RecommendationProvenanceError("inference feature registry hash mismatch")
    transform = provenance.get("feature_transform_contract")
    if not isinstance(transform, Mapping):
        raise RecommendationProvenanceError("inference feature transform contract is missing")
    verify_feature_transform_contract(
        transform,
        expected_registry_hash=registry_hash,
        expected_schema=expected_schema,
    )
    if expected_probability_transform_id is not None and provenance.get(
        "probability_transform_id"
    ) != expected_probability_transform_id:
        raise RecommendationProvenanceError(
            "inference probability transform identity mismatch"
        )
    rows = provenance.get("feature_rows")
    if not isinstance(rows, list) or not rows:
        raise RecommendationProvenanceError("inference feature rows are missing")
    canonical_schema = _canonical_feature_schema(transform.get("canonical_schema", ()))
    normalized_rows = _feature_rows_payload(
        rows,
        decision_date=decision_date,
        feature_schema=canonical_schema,
        row_ids_by_symbol=None,
    )
    symbols = [str(row["symbol"]) for row in normalized_rows]
    if len(symbols) != len(set(symbols)):
        raise RecommendationProvenanceError("inference feature row symbols are duplicated")
    if any(row["feature_as_of_date"] != feature_as_of_date for row in normalized_rows):
        raise RecommendationProvenanceError(
            "inference feature row cutoff does not match snapshot cutoff"
        )
    declared_symbols = sorted(
        {str(item).strip() for item in provenance.get("symbols", ()) if str(item).strip()}
    )
    if symbols != declared_symbols:
        raise RecommendationProvenanceError("inference provenance symbol identity mismatch")
    if expected_symbols is not None and symbols != sorted({str(item) for item in expected_symbols}):
        raise RecommendationProvenanceError("inference provenance symbol coverage mismatch")
    schema_hash = str(transform.get("feature_schema_hash") or "")
    if provenance.get("feature_schema_hash") != schema_hash:
        raise RecommendationProvenanceError("inference feature schema identity mismatch")
    builder_schema_hash = provenance.get("feature_builder_schema_hash")
    if builder_schema_hash != transform.get("feature_builder_schema_hash"):
        raise RecommendationProvenanceError(
            "inference feature builder schema identity mismatch"
        )
    expected_rows_hash = _feature_rows_hash(
        decision_date=decision_date,
        feature_registry_hash=registry_hash,
        feature_schema_hash=schema_hash,
        rows=normalized_rows,
    )
    if provenance.get("feature_rows_sha256") != expected_rows_hash:
        raise RecommendationProvenanceError("inference feature rows hash mismatch")
    expected_snapshot_fingerprint = _hash_payload(
        {"capture_decision_date": decision_date, "rows": normalized_rows}
    )
    if provenance.get("feature_snapshot_fingerprint") != expected_snapshot_fingerprint:
        raise RecommendationProvenanceError("inference feature snapshot fingerprint mismatch")
    pit = provenance.get("pit")
    if not isinstance(pit, Mapping):
        raise RecommendationProvenanceError("inference PIT payload is missing")
    if _date_text(pit.get("decision_date"), "inference.pit.decision_date") != decision_date:
        raise RecommendationProvenanceError("inference PIT decision date mismatch")
    if _date_text(
        pit.get("feature_as_of_date"), "inference.pit.feature_as_of_date"
    ) != feature_as_of_date:
        raise RecommendationProvenanceError("inference PIT feature cutoff mismatch")
    if pit.get("feature_as_of_before_decision") is not True:
        raise RecommendationProvenanceError("inference PIT cutoff assertion is invalid")
    if pit.get("feature_available_not_after_decision") is not True:
        raise RecommendationProvenanceError(
            "inference PIT availability assertion is invalid"
        )
    expected_pit_rows = [
        {
            "symbol": row["symbol"],
            "decision_date": row["decision_date"],
            "feature_as_of_date": row["feature_as_of_date"],
            "feature_available_date": row["feature_available_date"],
        }
        for row in normalized_rows
    ]
    if _json_ready(pit.get("rows")) != expected_pit_rows:
        raise RecommendationProvenanceError("inference PIT row timing identity mismatch")
    if provenance.get("inference_pit_hash") != _hash_payload(pit):
        raise RecommendationProvenanceError("inference PIT hash mismatch")
    if provenance.get("inference_source_hash") != _hash_payload(
        {
            "source_kind": _source_kind_from_provenance(provenance),
            "source_fingerprint": str(provenance.get("source_fingerprint") or ""),
            "raw_snapshot_content_sha256": provenance.get("raw_snapshot_content_sha256"),
            "feature_rows_sha256": provenance.get("feature_rows_sha256"),
            "feature_snapshot_fingerprint": provenance.get("feature_snapshot_fingerprint"),
            "source_tables": list(provenance.get("source_tables") or ()),
            "query_count": int(provenance.get("query_count") or 0),
        }
    ):
        raise RecommendationProvenanceError("inference source hash mismatch")
    raw_snapshot_hash = str(provenance.get("raw_snapshot_content_sha256") or "")
    _require_hash(raw_snapshot_hash, "raw snapshot content hash")
    raw_contract = provenance.get("raw_snapshot_contract")
    if not isinstance(raw_contract, Mapping):
        raise RecommendationProvenanceError("inference raw snapshot contract is missing")
    if raw_contract.get("source_content_scope") != "bounded_consumed_snapshot":
        raise RecommendationProvenanceError("inference raw snapshot content scope is invalid")
    if raw_contract.get("raw_snapshot_content_sha256") != raw_snapshot_hash:
        raise RecommendationProvenanceError("inference raw snapshot content identity mismatch")
    if raw_contract.get("source_kind") != _source_kind_from_provenance(provenance):
        raise RecommendationProvenanceError("inference raw snapshot source kind mismatch")
    builder_hash_value = provenance.get("feature_builder_schema_hash")
    if builder_hash_value not in (None, ""):
        _require_hash(str(builder_hash_value), "inference feature builder schema hash")
    source_contract_status = str(provenance.get("source_contract_status") or "")
    if source_contract_status not in {"not_supplied", "verified"}:
        raise RecommendationProvenanceError("inference source contract status is invalid")
    if (provenance.get("source_contract_binding") is None) != (
        source_contract_status == "not_supplied"
    ):
        raise RecommendationProvenanceError("inference source contract status is inconsistent")
    if provenance.get("source_contract_binding") is not None:
        verify_source_contract_binding(
            provenance["source_contract_binding"],
            decision_date=decision_date,
            feature_rows=normalized_rows,
            feature_registry_hash=registry_hash,
            feature_schema_hash=schema_hash,
            feature_builder_schema_hash=(
                str(builder_schema_hash) if builder_schema_hash not in (None, "") else None
            ),
            source_database=provenance.get("source_database"),
            history_start_date=provenance.get("history_start_date"),
        )
    declared_provenance_hash = str(provenance.get("provenance_hash") or "")
    _require_hash(declared_provenance_hash, "inference provenance hash")
    if declared_provenance_hash != _hash_payload(
        {key: value for key, value in provenance.items() if key != "provenance_hash"}
    ):
        raise RecommendationProvenanceError("inference provenance self-hash mismatch")


def validate_provenance_compatibility(
    training: Mapping[str, Any],
    inference: Mapping[str, Any],
    *,
    expected_cost_scenario_hash: str | None = None,
    expected_probability_transform_id: str | None = None,
) -> dict[str, Any]:
    """Compare shared contracts while keeping training and inference hashes distinct."""

    result: dict[str, Any] = {
        "schema_version": PROVENANCE_COMPATIBILITY_SCHEMA_VERSION,
        "status": "blocked",
        "checks": {},
    }
    if not isinstance(training, Mapping) or not isinstance(inference, Mapping):
        result["reason"] = "provenance_object_missing"
        return result
    result.update(
        {
            "training_source_hash": training.get("training_source_hash"),
            "training_pit_hash": training.get("training_pit_hash"),
            "inference_source_hash": inference.get("inference_source_hash"),
            "inference_pit_hash": inference.get("inference_pit_hash"),
        }
    )
    if training.get("status") == "legacy_unproven":
        result["status"] = "legacy_unproven"
        result["reason"] = "training_provenance_legacy_unproven"
        return result
    if training.get("status") != "verified" or inference.get("status") != "verified":
        result["reason"] = "verified_provenance_missing"
        return result
    required_hashes = {
        "training_source_hash": training.get("training_source_hash"),
        "training_pit_hash": training.get("training_pit_hash"),
        "inference_source_hash": inference.get("inference_source_hash"),
        "inference_pit_hash": inference.get("inference_pit_hash"),
    }
    missing_hashes = [key for key, value in required_hashes.items() if value in (None, "")]
    for key, value in required_hashes.items():
        if value not in (None, ""):
            try:
                _require_hash(str(value), key)
            except RecommendationProvenanceError:
                result["reason"] = f"invalid_{key}"
                return result
    if missing_hashes:
        result["reason"] = "provenance_hash_missing:" + ",".join(missing_hashes)
        return result
    comparisons = {
        "feature_registry_hash": (
            training.get("feature_registry_hash"), inference.get("feature_registry_hash")
        ),
        "feature_schema_hash": (
            training.get("feature_schema_hash"), inference.get("feature_schema_hash")
        ),
        "feature_transform_contract_hash": (
            _contract_hash(training.get("feature_transform_contract")),
            _contract_hash(inference.get("feature_transform_contract")),
        ),
        "feature_transform_contract_id": (
            _contract_id(training.get("feature_transform_contract")),
            _contract_id(inference.get("feature_transform_contract")),
        ),
    }
    if expected_cost_scenario_hash is not None:
        comparisons["cost_scenario_hash.training"] = (
            training.get("cost_scenario_hash"),
            expected_cost_scenario_hash,
        )
        comparisons["cost_scenario_hash.inference"] = (
            inference.get("cost_scenario_hash"),
            expected_cost_scenario_hash,
        )
    if expected_probability_transform_id is not None:
        comparisons["probability_transform_id"] = (
            inference.get("probability_transform_id"),
            expected_probability_transform_id,
        )
    missing_shared = [
        key
        for key, (left, right) in comparisons.items()
        if key
        in {
            "feature_registry_hash",
            "feature_schema_hash",
            "feature_transform_contract_hash",
            "feature_transform_contract_id",
        }
        and (left in (None, "") or right in (None, ""))
    ]
    result["checks"] = {
        key: {
            "left": left,
            "right": right,
            "match": left == right and key not in missing_shared,
        }
        for key, (left, right) in comparisons.items()
    }
    if missing_shared:
        result["reason"] = "shared_contract_field_missing:" + ",".join(missing_shared)
        return result
    mismatches = [key for key, values in result["checks"].items() if not values["match"]]
    if mismatches:
        result["reason"] = "shared_contract_mismatch:" + ",".join(mismatches)
        return result
    result["status"] = "verified"
    result["reason"] = "shared_feature_transform_and_cost_contracts_match"
    return result


def build_inference_projection_receipt(
    *,
    decision_date: str,
    result_id: str | None,
    candidate_identity: Mapping[str, Any],
    training_provenance: Mapping[str, Any],
    inference_provenance: Mapping[str, Any],
    compatibility: Mapping[str, Any],
    projections: Sequence[Mapping[str, Any]],
    selection_contract: Mapping[str, Any] | None = None,
) -> "RecommendationInferenceProjectionReceipt":
    """Build one immutable receipt for the exact visible projection batch."""

    day = _date_text(decision_date, "decision_date")
    candidate = _json_mapping(candidate_identity)
    candidate_id = str(candidate.get("candidate_id") or "").strip()
    if not candidate_id:
        raise RecommendationProvenanceError("projection receipt candidate identity is missing")
    declared_model_id = str(candidate.get("model_id") or "").strip()
    if declared_model_id and declared_model_id != candidate_id:
        raise RecommendationProvenanceError(
            "projection receipt candidate model identity mismatch"
        )
    verify_inference_provenance(
        inference_provenance,
        expected_decision_date=day,
        expected_probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    rows = [_json_mapping(item) for item in projections]
    if not rows:
        raise RecommendationProvenanceError("projection receipt rows are empty")
    rows.sort(key=lambda item: str(item.get("stock_code") or ""))
    stock_codes = [str(item.get("stock_code") or "") for item in rows]
    if any(not code for code in stock_codes) or len(stock_codes) != len(set(stock_codes)):
        raise RecommendationProvenanceError("projection receipt stock identity is invalid")
    model_versions = {
        str(item.get("model_version") or "").strip()
        for item in rows
        if str(item.get("model_version") or "").strip()
    }
    if model_versions and model_versions != {candidate_id}:
        raise RecommendationProvenanceError(
            "projection receipt candidate/model race detected"
        )
    cost_hashes = {
        str(item.get("cost_scenario_hash") or "")
        for item in rows
        if str(item.get("cost_scenario_hash") or "")
    }
    if len(cost_hashes) > 1:
        raise RecommendationProvenanceError("projection receipt cost lane is mixed")
    selection = {
        "authority": PROJECTION_SELECTION_AUTHORITY,
        "score_kind": PROJECTION_SELECTION_SCORE_KIND,
        "percentile_kind": PROJECTION_SELECTION_PERCENTILE_KIND,
        "model_ranking_kind": PROJECTION_MODEL_RANKING_KIND,
        "top_n_changed_by_model": False,
        **_json_mapping(selection_contract or {}),
    }
    expected_selection = {
        "authority": PROJECTION_SELECTION_AUTHORITY,
        "score_kind": PROJECTION_SELECTION_SCORE_KIND,
        "percentile_kind": PROJECTION_SELECTION_PERCENTILE_KIND,
        "model_ranking_kind": PROJECTION_MODEL_RANKING_KIND,
        "top_n_changed_by_model": False,
    }
    if any(selection.get(key) != value for key, value in expected_selection.items()):
        raise RecommendationProvenanceError(
            "projection receipt selection contract is invalid"
        )
    _validate_candidate_identity(candidate)
    training_status = str(training_provenance.get("status") or "")
    if training_status not in {"verified", "legacy_unproven"}:
        raise RecommendationProvenanceError(
            "projection receipt training provenance status is invalid"
        )
    row_costs = {
        str(item.get("cost_scenario_hash") or "")
        for item in rows
        if str(item.get("cost_scenario_hash") or "")
    }
    if len(row_costs) > 1:
        raise RecommendationProvenanceError("projection receipt cost lane is mixed")
    candidate_cost = str(candidate.get("cost_scenario_hash") or "")
    training_cost = str(training_provenance.get("cost_scenario_hash") or "")
    inference_cost = str(inference_provenance.get("cost_scenario_hash") or "")
    if training_status == "verified":
        if not training_cost or not inference_cost or not row_costs:
            raise RecommendationProvenanceError(
                "verified projection receipt cost identity is incomplete"
            )
        _require_hash(training_cost, "training cost scenario hash")
        _require_hash(inference_cost, "inference cost scenario hash")
        if inference_cost != training_cost or row_costs != {training_cost}:
            raise RecommendationProvenanceError(
                "verified projection receipt cost identity mismatch"
            )
    if candidate_cost:
        _require_hash(candidate_cost, "candidate cost scenario hash")
        expected_cost = training_cost or inference_cost or next(iter(row_costs), "")
        if expected_cost and candidate_cost != expected_cost:
            raise RecommendationProvenanceError(
                "projection receipt candidate cost identity mismatch"
            )
    expected_cost = training_cost or inference_cost or next(iter(row_costs), "")
    if expected_cost and row_costs and row_costs != {expected_cost}:
        raise RecommendationProvenanceError("projection receipt cost identity mismatch")
    expected_compatibility = validate_provenance_compatibility(
        training_provenance,
        inference_provenance,
        expected_cost_scenario_hash=(expected_cost or None),
        expected_probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    declared_compatibility = _json_mapping(compatibility)
    if declared_compatibility != expected_compatibility:
        raise RecommendationProvenanceError(
            "projection receipt compatibility declaration mismatch"
        )
    if training_status == "verified" and expected_compatibility.get("status") != "verified":
        raise RecommendationProvenanceError(
            "verified training projection receipt compatibility is not verified"
        )
    projection_rows_hash = _hash_payload(rows)
    exact_result_identity = {
        "result_id": str(result_id or "") or None,
        "decision_date": day,
        "candidate_id": candidate_id,
        "stock_codes": stock_codes,
        "projection_rows_sha256": projection_rows_hash,
    }
    body: dict[str, Any] = {
        "schema_version": PROJECTION_RECEIPT_SCHEMA_VERSION,
        "receipt_kind": "recommendation_inference_projection",
        "decision_date": day,
        "result_id": str(result_id or "") or None,
        "result_identity_hash": _hash_payload(exact_result_identity),
        "candidate_identity": candidate,
        "training_provenance": _json_mapping(training_provenance),
        "inference_provenance": _json_mapping(inference_provenance),
        "provenance_compatibility": _json_mapping(compatibility),
        "selection_contract": selection,
        "cost_scenario_hash": next(iter(cost_hashes), None),
        "projection_rows_sha256": projection_rows_hash,
        "projections": rows,
        "shadow_only": True,
        "formal_order_allowed": False,
        "production_action_allowed": False,
    }
    receipt_hash = _hash_payload(body)
    return RecommendationInferenceProjectionReceipt(
        payload=body,
        receipt_hash=receipt_hash,
    )


@dataclass(frozen=True)
class RecommendationInferenceProjectionReceipt:
    payload: Mapping[str, Any]
    receipt_hash: str
    receipt_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = _json_mapping(self.payload)
        payload["receipt_hash"] = self.receipt_hash
        return payload


def inference_projection_receipt_path(
    learning_root: str | Path,
    receipt: RecommendationInferenceProjectionReceipt,
) -> Path:
    body = receipt.payload
    day = _date_text(body.get("decision_date"), "receipt.decision_date")
    candidate_id = _safe_component(str(body.get("candidate_identity", {}).get("candidate_id") or "candidate"))
    digest = receipt.receipt_hash.split(":", 1)[1]
    return Path(learning_root).expanduser().resolve() / "inference_projection" / day / candidate_id / f"{digest}.json"


def persist_inference_projection_receipt(
    learning_root: str | Path,
    receipt: RecommendationInferenceProjectionReceipt,
) -> Path:
    """Publish an immutable receipt; a conflicting rewrite is rejected."""

    destination = inference_projection_receipt_path(learning_root, receipt)
    encoded = (
        json.dumps(receipt.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    _write_create_only(destination, encoded)
    return destination


def read_inference_projection_receipt(
    path: str | Path,
    *,
    expected_receipt_hash: str | None = None,
    expected_decision_date: str | None = None,
    expected_candidate_id: str | None = None,
    expected_result_id: str | None = None,
    expected_stock_code: str | None = None,
    expected_cost_scenario_hash: str | None = None,
) -> RecommendationInferenceProjectionReceipt:
    """Read, hash-check, and identity-check one immutable projection receipt."""

    receipt_path = Path(path).expanduser().resolve()
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise RecommendationProvenanceError("projection receipt is missing or symlinked")
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecommendationProvenanceError("projection receipt is unreadable") from exc
    if not isinstance(payload, Mapping):
        raise RecommendationProvenanceError("projection receipt must be an object")
    supplied_hash = str(payload.get("receipt_hash") or "")
    _require_hash(supplied_hash, "projection receipt hash")
    if expected_receipt_hash is not None and supplied_hash != expected_receipt_hash:
        raise RecommendationProvenanceError("projection receipt hash mismatch")
    if receipt_path.stem != supplied_hash.split(":", 1)[1]:
        raise RecommendationProvenanceError("projection receipt filename hash mismatch")
    body = dict(payload)
    body.pop("receipt_hash", None)
    _validate_receipt_body(body)
    actual_hash = _hash_payload(body)
    if actual_hash != supplied_hash:
        raise RecommendationProvenanceError("projection receipt body hash mismatch")
    day = str(body.get("decision_date") or "")
    if expected_decision_date is not None and day != _date_text(expected_decision_date, "expected_decision_date"):
        raise RecommendationProvenanceError("projection receipt decision date mismatch")
    candidate_id = str(body.get("candidate_identity", {}).get("candidate_id") or "")
    if expected_candidate_id is not None and candidate_id != str(expected_candidate_id):
        raise RecommendationProvenanceError("projection receipt candidate identity mismatch")
    result_id = str(body.get("result_id") or "")
    if expected_result_id is not None and result_id != str(expected_result_id):
        raise RecommendationProvenanceError("projection receipt result identity mismatch")
    if expected_cost_scenario_hash is not None and body.get("cost_scenario_hash") != expected_cost_scenario_hash:
        raise RecommendationProvenanceError("projection receipt cost scenario mismatch")
    if expected_stock_code is not None:
        if str(expected_stock_code) not in {
            str(item.get("stock_code") or "") for item in body["projections"]
        }:
            raise RecommendationProvenanceError("projection receipt stock identity mismatch")
    return RecommendationInferenceProjectionReceipt(
        payload=body,
        receipt_hash=supplied_hash,
        receipt_path=str(receipt_path),
    )


def find_inference_projection_receipts(
    learning_root: str | Path,
    *,
    decision_date: str | None = None,
    candidate_id: str | None = None,
    result_id: str | None = None,
    stock_code: str | None = None,
    cost_scenario_hash: str | None = None,
) -> tuple[RecommendationInferenceProjectionReceipt, ...]:
    """Find exact receipt matches; invalid matching receipts fail closed."""

    root = Path(learning_root).expanduser().resolve() / "inference_projection"
    if not root.is_dir():
        return ()
    paths = sorted(root.glob("**/*.json"))
    if decision_date is not None:
        expected_day = _date_text(decision_date, "expected_decision_date")
        paths = [path for path in paths if path.parent.parent.name == expected_day]
    if candidate_id is not None:
        expected_candidate = _safe_component(str(candidate_id))
        paths = [path for path in paths if path.parent.name == expected_candidate]
    receipts: list[RecommendationInferenceProjectionReceipt] = []
    for path in paths:
        receipt = read_inference_projection_receipt(path)
        body = receipt.payload
        if decision_date is not None and body.get("decision_date") != _date_text(
            decision_date, "expected_decision_date"
        ):
            continue
        if candidate_id is not None and str(
            body.get("candidate_identity", {}).get("candidate_id") or ""
        ) != str(candidate_id):
            continue
        if result_id is not None and str(body.get("result_id") or "") != str(result_id):
            continue
        if cost_scenario_hash is not None and body.get("cost_scenario_hash") != cost_scenario_hash:
            continue
        if stock_code is not None and str(stock_code) not in {
            str(item.get("stock_code") or "") for item in body.get("projections", ())
        }:
            continue
        receipts.append(receipt)
    return tuple(receipts)


def verify_source_contract_binding(
    binding: Mapping[str, Any],
    *,
    decision_date: str,
    feature_rows: Sequence[Mapping[str, Any]],
    feature_registry_hash: str,
    feature_schema_hash: str,
    feature_builder_schema_hash: str | None = None,
    source_database: str | None = None,
    history_start_date: str | None = None,
) -> None:
    """Verify the optional prospective contract against exact consumed rows."""

    if not isinstance(binding, Mapping):
        raise RecommendationProvenanceError("source contract binding is not an object")
    if binding.get("schema_version") != "recommendation-calibration-capture-source-binding.v1":
        raise RecommendationProvenanceError("source contract binding schema is unsupported")
    if binding.get("historical_pit_eligible") is not False:
        raise RecommendationProvenanceError("source contract binding cannot claim historical PIT")
    if binding.get("price_up_prospective_status") != "ready":
        raise RecommendationProvenanceError("source contract prospective lane is not ready")
    contract_path = Path(str(binding.get("contract_path") or "")).expanduser().resolve()
    if contract_path.is_symlink() or not contract_path.is_file():
        raise RecommendationProvenanceError("source contract receipt is missing")
    file_hash = str(binding.get("contract_file_sha256") or "")
    content_hash = str(binding.get("contract_content_sha256") or "")
    _require_hash(file_hash, "source contract file hash")
    _require_hash(content_hash, "source contract content hash")
    if _sha256_file(contract_path) != file_hash:
        raise RecommendationProvenanceError("source contract file hash mismatch")
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecommendationProvenanceError("source contract receipt is unreadable") from exc
    if not isinstance(contract, Mapping):
        raise RecommendationProvenanceError("source contract payload is invalid")
    contract_body = {
        key: value
        for key, value in contract.items()
        if key not in {"contract_sha256", "checked_at"}
    }
    if contract.get("contract_sha256") != _hash_payload(contract_body):
        raise RecommendationProvenanceError("source contract content self-hash mismatch")
    if contract.get("contract_sha256") != content_hash:
        raise RecommendationProvenanceError("source contract content hash mismatch")
    day = _date_text(decision_date, "decision_date")
    if _date_text(contract.get("decision_date"), "source contract decision_date") != day:
        raise RecommendationProvenanceError("source contract decision date mismatch")
    expected_symbols = sorted({str(row.get("symbol") or "") for row in feature_rows})
    contract_symbols = sorted({str(item) for item in contract.get("symbols", ()) if str(item).strip()})
    binding_symbols = sorted({str(item) for item in binding.get("symbols", ()) if str(item).strip()})
    if not expected_symbols or expected_symbols != contract_symbols or expected_symbols != binding_symbols:
        raise RecommendationProvenanceError("source contract symbol coverage mismatch")
    technical = contract.get("technical")
    technical = technical if isinstance(technical, Mapping) else {}
    snapshot = technical.get("prospective_feature_snapshot")
    if not isinstance(snapshot, Mapping):
        raise RecommendationProvenanceError("source contract feature snapshot is missing")
    snapshot_content_hash = str(snapshot.get("content_sha256") or "")
    _require_hash(snapshot_content_hash, "source contract feature snapshot content hash")
    if snapshot_content_hash != binding.get("feature_snapshot_content_sha256"):
        raise RecommendationProvenanceError("source contract feature snapshot content identity mismatch")
    snapshot_body = {key: value for key, value in snapshot.items() if key != "content_sha256"}
    if snapshot_content_hash != _hash_payload(snapshot_body):
        raise RecommendationProvenanceError("source contract feature snapshot self-hash mismatch")
    if snapshot.get("feature_registry_hash") != feature_registry_hash:
        raise RecommendationProvenanceError("source contract feature registry identity mismatch")
    expected_source_schema_hash = feature_builder_schema_hash or feature_schema_hash
    if snapshot.get("feature_schema_hash") != expected_source_schema_hash:
        raise RecommendationProvenanceError("source contract feature schema identity mismatch")
    if source_database is not None and str(snapshot.get("source_db") or "") != str(Path(source_database).expanduser().resolve()):
        raise RecommendationProvenanceError("source contract source database identity mismatch")
    if history_start_date is not None and _date_text(snapshot.get("history_start_date"), "source contract history_start_date") != _date_text(history_start_date, "history_start_date"):
        raise RecommendationProvenanceError("source contract history start identity mismatch")
    expected_rows = snapshot.get("rows")
    if not isinstance(expected_rows, list):
        raise RecommendationProvenanceError("source contract feature snapshot rows are missing")
    expected_rows_hash = _source_contract_feature_rows_hash(
        source_db=str(snapshot.get("source_db") or ""),
        decision_date=day,
        history_start_date=str(snapshot.get("history_start_date") or ""),
        feature_registry_hash=feature_registry_hash,
        feature_schema_hash=expected_source_schema_hash,
        symbols=expected_symbols,
        rows=feature_rows,
    )
    if snapshot.get("rows_sha256") != expected_rows_hash:
        raise RecommendationProvenanceError("source contract feature rows hash mismatch")
    if binding.get("feature_snapshot_rows_sha256") != expected_rows_hash:
        raise RecommendationProvenanceError("source contract feature rows binding mismatch")
    expected_by_symbol = {
        str(row.get("symbol") or ""): row
        for row in expected_rows
        if isinstance(row, Mapping) and str(row.get("symbol") or "")
    }
    actual_by_symbol = {str(row.get("symbol") or ""): row for row in feature_rows}
    if set(expected_by_symbol) != set(actual_by_symbol):
        raise RecommendationProvenanceError("source contract feature row coverage mismatch")
    for symbol, actual in actual_by_symbol.items():
        expected = expected_by_symbol[symbol]
        for key in ("decision_date", "feature_as_of_date", "feature_available_date"):
            if str(actual.get(key) or "")[:10] != str(expected.get(key) or "")[:10]:
                raise RecommendationProvenanceError("source contract feature timing mismatch")
        if list(actual.get("feature_values") or ()) != list(expected.get("feature_values") or ()):
            raise RecommendationProvenanceError("source contract feature values mismatch")


def _source_contract_feature_rows_hash(
    *,
    source_db: str,
    decision_date: str,
    history_start_date: str,
    feature_registry_hash: str,
    feature_schema_hash: str,
    symbols: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> str:
    canonical_rows = [
        {
            "symbol": row.get("symbol"),
            "decision_date": row.get("decision_date"),
            "feature_as_of_date": row.get("feature_as_of_date"),
            "feature_available_date": row.get("feature_available_date"),
            "feature_ids": list(row.get("feature_ids") or ()),
            "feature_values": list(row.get("feature_values") or ()),
            "snapshot_hash": row.get("snapshot_hash", ""),
        }
        for row in sorted(rows, key=lambda item: str(item.get("symbol") or ""))
    ]
    return _hash_payload(
        {
            "component": "prospective_recommendation_features",
            "source_db": source_db,
            "decision_date": decision_date,
            "history_start_date": history_start_date,
            "feature_registry_hash": feature_registry_hash,
            "feature_schema_hash": feature_schema_hash,
            "symbols": list(symbols),
            "rows": canonical_rows,
        }
    )


def _feature_rows_hash(
    *,
    decision_date: str,
    feature_registry_hash: str,
    feature_schema_hash: str,
    rows: Sequence[Mapping[str, Any]],
) -> str:
    return _hash_payload(
        {
            "schema_version": INFERENCE_PROVENANCE_SCHEMA_VERSION,
            "decision_date": decision_date,
            "feature_registry_hash": feature_registry_hash,
            "feature_schema_hash": feature_schema_hash,
            "rows": list(rows),
        }
    )


def _feature_rows_payload(
    rows: Sequence[Any],
    *,
    decision_date: str,
    feature_schema: tuple[tuple[str, str, str], ...],
    row_ids_by_symbol: Mapping[str, str] | None,
) -> list[dict[str, Any]]:
    expected_ids = [item[0] for item in feature_schema]
    normalized: list[dict[str, Any]] = []
    for raw in rows:
        symbol = str(_value(raw, "symbol") or "").strip()
        if not symbol:
            raise RecommendationProvenanceError("inference feature row symbol is missing")
        raw_values = _value(raw, "values")
        if raw_values is None:
            raw_values = _value(raw, "feature_values")
        if isinstance(raw_values, Mapping):
            by_id = dict(raw_values)
        else:
            try:
                pairs = list(raw_values or ())
            except TypeError as exc:
                raise RecommendationProvenanceError("inference feature row values are invalid") from exc
            raw_ids = _value(raw, "feature_ids")
            if (
                isinstance(raw_ids, (list, tuple))
                and len(raw_ids) == len(pairs)
                and all(not isinstance(item, (list, tuple)) or len(item) != 2 for item in pairs)
            ):
                by_id = {str(feature_id): value for feature_id, value in zip(raw_ids, pairs)}
            else:
                by_id = {
                    str(item[0]): item[1]
                    for item in pairs
                    if isinstance(item, (list, tuple)) and len(item) == 2
                }
        if set(by_id) != set(expected_ids):
            raise RecommendationProvenanceError(f"inference feature schema mismatch: {symbol}")
        row_decision = _date_text(_value(raw, "decision_date") or decision_date, f"feature row {symbol}.decision_date")
        if row_decision != decision_date:
            raise RecommendationProvenanceError(f"inference feature row decision date mismatch: {symbol}")
        as_of = _date_text(
            _value(raw, "feature_as_of_date") or _value(raw, "feature_as_of") or "",
            f"feature row {symbol}.feature_as_of_date",
        )
        available = _date_text(
            _value(raw, "feature_available_date") or _value(raw, "available_date") or "",
            f"feature row {symbol}.feature_available_date",
        )
        if date.fromisoformat(as_of) >= date.fromisoformat(decision_date):
            raise RecommendationProvenanceError(f"inference feature row is future-looking: {symbol}")
        if date.fromisoformat(available) > date.fromisoformat(decision_date):
            raise RecommendationProvenanceError(f"inference feature row availability is future-looking: {symbol}")
        values = [by_id[item] for item in expected_ids]
        if any(value is not None and (isinstance(value, bool) or not isinstance(value, int)) for value in values):
            raise RecommendationProvenanceError(f"inference feature values are not integer units: {symbol}")
        row_id = str(
            _value(raw, "row_id")
            or (row_ids_by_symbol or {}).get(symbol)
            or f"recommendation-inference:{decision_date}:{symbol}"
        )
        normalized.append(
            {
                "row_id": row_id,
                "symbol": symbol,
                "decision_date": row_decision,
                "feature_as_of_date": as_of,
                "feature_available_date": available,
                "feature_ids": expected_ids,
                "feature_values": values,
                "snapshot_hash": str(_value(raw, "snapshot_hash") or ""),
            }
        )
    normalized.sort(key=lambda item: (str(item["symbol"]), str(item["row_id"])))
    return normalized


def _raw_snapshot_payload(snapshot: Any, decision_date: str, feature_as_of_date: str) -> dict[str, Any]:
    return {
        "schema_version": INFERENCE_PROVENANCE_SCHEMA_VERSION,
        "decision_date": decision_date,
        "feature_as_of_date": feature_as_of_date,
        "source_tables": list(_value(snapshot, "source_tables") or ()),
        "query_count": int(_value(snapshot, "query_count") or 0),
        "prices": _json_ready(_value(snapshot, "prices") or ()),
        "technicals": _json_ready(_value(snapshot, "technicals") or ()),
        "market": _json_ready(_value(snapshot, "market") or ()),
        "industries": _json_ready(_value(snapshot, "industries") or ()),
    }


def _source_kind_from_provenance(provenance: Mapping[str, Any]) -> str:
    raw_contract = provenance.get("raw_snapshot_contract")
    if isinstance(raw_contract, Mapping) and raw_contract.get("source_kind"):
        return str(raw_contract["source_kind"])
    # The producer records the concrete snapshot type in source_identity.  Keep
    # this fallback stable for persisted v1 payloads that only carried the hash.
    return str(provenance.get("source_kind") or "HistoricalRawSnapshot")


def _validate_receipt_body(body: Mapping[str, Any]) -> None:
    if body.get("schema_version") != PROJECTION_RECEIPT_SCHEMA_VERSION:
        raise RecommendationProvenanceError("projection receipt schema is unsupported")
    if body.get("receipt_kind") != "recommendation_inference_projection":
        raise RecommendationProvenanceError("projection receipt kind is invalid")
    if body.get("shadow_only") is not True:
        raise RecommendationProvenanceError("projection receipt shadow flag is invalid")
    if body.get("formal_order_allowed") is not False or body.get("production_action_allowed") is not False:
        raise RecommendationProvenanceError("projection receipt production flags are invalid")
    day = _date_text(body.get("decision_date"), "receipt.decision_date")
    candidate = body.get("candidate_identity")
    if not isinstance(candidate, Mapping) or not str(candidate.get("candidate_id") or ""):
        raise RecommendationProvenanceError("projection receipt candidate identity is missing")
    _validate_candidate_identity(candidate)
    effective_date = candidate.get("effective_date")
    if effective_date not in (None, "") and _date_text(
        effective_date, "candidate.effective_date"
    ) > day:
        raise RecommendationProvenanceError(
            "projection receipt candidate is not effective on decision date"
        )
    training = body.get("training_provenance")
    if not isinstance(training, Mapping):
        raise RecommendationProvenanceError("projection receipt training provenance is missing")
    if training.get("status") not in {"verified", "legacy_unproven"}:
        raise RecommendationProvenanceError("projection receipt training provenance status is invalid")
    _verify_receipt_training_provenance(
        training,
        candidate_identity=candidate,
        decision_date=day,
    )
    inference = body.get("inference_provenance")
    if not isinstance(inference, Mapping):
        raise RecommendationProvenanceError("projection receipt inference provenance is missing")
    verify_inference_provenance(
        inference,
        expected_decision_date=day,
        expected_probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    compatibility = body.get("provenance_compatibility")
    if not isinstance(compatibility, Mapping) or compatibility.get("status") not in {"verified", "legacy_unproven", "blocked"}:
        raise RecommendationProvenanceError("projection receipt compatibility status is invalid")
    declared_cost = str(body.get("cost_scenario_hash") or "")
    if declared_cost:
        _require_hash(declared_cost, "projection receipt cost scenario hash")
    training_status = str(training.get("status") or "")
    if training_status == "verified" and not declared_cost:
        raise RecommendationProvenanceError(
            "verified projection receipt cost identity is missing"
        )
    expected_compatibility = validate_provenance_compatibility(
        training,
        inference,
        expected_cost_scenario_hash=declared_cost or None,
        expected_probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    if _json_mapping(compatibility) != expected_compatibility:
        raise RecommendationProvenanceError(
            "projection receipt compatibility declaration mismatch"
        )
    if training_status == "verified" and expected_compatibility.get("status") != "verified":
        raise RecommendationProvenanceError(
            "verified projection receipt compatibility is not verified"
        )
    selection = body.get("selection_contract")
    expected_selection = {
        "authority": PROJECTION_SELECTION_AUTHORITY,
        "score_kind": PROJECTION_SELECTION_SCORE_KIND,
        "percentile_kind": PROJECTION_SELECTION_PERCENTILE_KIND,
        "model_ranking_kind": PROJECTION_MODEL_RANKING_KIND,
        "top_n_changed_by_model": False,
    }
    if not isinstance(selection, Mapping) or any(
        selection.get(key) != value for key, value in expected_selection.items()
    ):
        raise RecommendationProvenanceError("projection receipt selection contract is invalid")
    rows = body.get("projections")
    if not isinstance(rows, list) or not rows:
        raise RecommendationProvenanceError("projection receipt projections are missing")
    normalized_rows = [_json_mapping(item) for item in rows]
    normalized_rows.sort(key=lambda item: str(item.get("stock_code") or ""))
    if body.get("projection_rows_sha256") != _hash_payload(normalized_rows):
        raise RecommendationProvenanceError("projection receipt projection rows hash mismatch")
    candidate_id = str(candidate.get("candidate_id") or "")
    for row in normalized_rows:
        if not str(row.get("stock_code") or ""):
            raise RecommendationProvenanceError("projection receipt row stock identity is missing")
        if row.get("status") == "active_candidate" and str(row.get("model_version") or "") != candidate_id:
            raise RecommendationProvenanceError("projection receipt row candidate identity mismatch")
    expected_result_identity = {
        "result_id": str(body.get("result_id") or "") or None,
        "decision_date": day,
        "candidate_id": candidate_id,
        "stock_codes": [str(item.get("stock_code") or "") for item in normalized_rows],
        "projection_rows_sha256": body.get("projection_rows_sha256"),
    }
    if body.get("result_identity_hash") != _hash_payload(expected_result_identity):
        raise RecommendationProvenanceError("projection receipt result identity hash mismatch")
    row_costs = {
        str(item.get("cost_scenario_hash") or "")
        for item in normalized_rows
        if str(item.get("cost_scenario_hash") or "")
    }
    if len(row_costs) > 1:
        raise RecommendationProvenanceError("projection receipt cost lane is mixed")
    if declared_cost not in (None, "") and row_costs != {declared_cost}:
        raise RecommendationProvenanceError("projection receipt cost identity mismatch")
    if training_status == "verified":
        training_cost = str(training.get("cost_scenario_hash") or "")
        inference_cost = str(inference.get("cost_scenario_hash") or "")
        if (
            not training_cost
            or not inference_cost
            or training_cost != declared_cost
            or inference_cost != declared_cost
            or row_costs != {declared_cost}
        ):
            raise RecommendationProvenanceError(
                "verified projection receipt cost identity mismatch"
            )
    elif declared_cost and inference.get("cost_scenario_hash") not in (None, "", declared_cost):
        raise RecommendationProvenanceError("projection receipt inference cost identity mismatch")


def _verify_receipt_training_provenance(
    training: Mapping[str, Any],
    *,
    candidate_identity: Mapping[str, Any],
    decision_date: str,
) -> None:
    """Re-read the declared lineage instead of trusting receipt DTO fields."""

    status = str(training.get("status") or "")
    if status not in {"verified", "legacy_unproven"}:
        raise RecommendationProvenanceError("training provenance status is invalid")
    p1_values = [
        training.get("training_source_hash"),
        training.get("training_pit_hash"),
        training.get("feature_transform_contract"),
        training.get("feature_transform_contract_hash"),
    ]
    p1_declared = any(value not in (None, "") for value in p1_values)
    if status == "verified":
        if not all(value not in (None, "") for value in p1_values):
            raise RecommendationProvenanceError(
                "verified training provenance declarations are incomplete"
            )
        if not isinstance(training.get("feature_transform_contract"), Mapping):
            raise RecommendationProvenanceError(
                "verified training feature transform contract is missing"
            )
        if training.get("feature_transform_contract_hash") != _contract_hash(
            training.get("feature_transform_contract")
        ):
            raise RecommendationProvenanceError(
                "training feature transform contract hash is inconsistent"
            )
        for key in (
            "training_source_hash",
            "training_pit_hash",
            "feature_transform_contract_hash",
            "feature_registry_hash",
            "feature_schema_hash",
        ):
            if training.get(key) in (None, ""):
                raise RecommendationProvenanceError(
                    f"verified training provenance field is missing: {key}"
                )
            if key.endswith("hash"):
                _require_hash(str(training.get(key)), f"training {key}")
    elif p1_declared:
        raise RecommendationProvenanceError(
            "legacy training provenance contains partial P1 declarations"
        )

    nested_identity = candidate_identity.get("training_provenance")
    nested_identity = nested_identity if isinstance(nested_identity, Mapping) else {}
    declared_pairs = (
        (
            "manifest_hash",
            "manifest_path",
            training.get("manifest_hash"),
            training.get("manifest_path"),
        ),
        (
            "candidate_lineage_manifest_hash",
            "candidate_lineage_manifest_path",
            candidate_identity.get("training_lineage_manifest_hash")
            or nested_identity.get("manifest_hash"),
            candidate_identity.get("training_lineage_manifest_path")
            or nested_identity.get("manifest_path"),
        ),
    )
    pairs = [
        (str(left or "").strip(), str(right or "").strip())
        for _, _, left, right in declared_pairs
        if left not in (None, "") or right not in (None, "")
    ]
    for manifest_hash, manifest_path in pairs:
        if bool(manifest_hash) != bool(manifest_path):
            raise RecommendationProvenanceError(
                "training lineage manifest hash/path declaration is incomplete"
            )
    if len(pairs) > 1 and pairs[0] != pairs[1]:
        raise RecommendationProvenanceError(
            "training lineage manifest identity is inconsistent"
        )
    manifest_hash, manifest_path = pairs[0] if pairs else ("", "")
    if status == "verified" and (not manifest_hash or not manifest_path):
        raise RecommendationProvenanceError(
            "verified training provenance manifest declaration is missing"
        )
    if not manifest_hash and not manifest_path:
        return
    _require_hash(manifest_hash, "training lineage manifest hash")
    lineage_path = Path(manifest_path).expanduser().resolve()
    if lineage_path.is_symlink() or not lineage_path.is_file():
        raise RecommendationProvenanceError(
            "training lineage manifest is missing or symlinked"
        )
    try:
        from ml_module.recommendation_training_lineage import (
            read_recommendation_training_lineage,
        )

        expected_dataset = str(
            training.get("dataset_hash")
            or candidate_identity.get("dataset_hash")
            or ""
        ) or None
        expected_candidate = str(candidate_identity.get("candidate_id") or "") or None
        lineage = read_recommendation_training_lineage(
            lineage_path,
            expected_manifest_hash=manifest_hash,
            expected_dataset_hash=expected_dataset,
            expected_candidate_id=expected_candidate,
        )
        lineage_day = _date_text(lineage.payload.get("decision_date"), "training.decision_date")
        if lineage_day > decision_date:
            raise RecommendationProvenanceError(
                "training lineage decision date is after receipt decision date"
            )
        rebuilt = build_training_provenance(
            lineage_payload=lineage.payload,
            manifest_hash=lineage.manifest_hash,
            manifest_path=str(lineage_path),
            candidate_payload=candidate_identity,
        )
    except RecommendationProvenanceError:
        raise
    except Exception as exc:  # noqa: BLE001 - readback must fail closed
        raise RecommendationProvenanceError(
            "training lineage readback failed"
        ) from exc
    if str(rebuilt.get("status") or "") != status:
        raise RecommendationProvenanceError(
            "training lineage status does not match receipt"
        )
    compare_keys = (
        "manifest_hash",
        "manifest_path",
        "training_source_hash",
        "training_pit_hash",
        "feature_registry_hash",
        "feature_schema_hash",
        "feature_transform_contract_hash",
        "dataset_id",
        "dataset_hash",
        "decision_date",
        "training_as_of",
        "training_semantics",
        "decision_time_eligible",
        "research_only",
        "cost_scenario_hash",
    )
    for key in compare_keys:
        left = rebuilt.get(key)
        right = training.get(key)
        if key == "manifest_path" and left not in (None, "") and right not in (None, ""):
            left = str(Path(str(left)).expanduser().resolve())
            right = str(Path(str(right)).expanduser().resolve())
        if left != right:
            raise RecommendationProvenanceError(
                f"training lineage readback field mismatch: {key}"
            )
    if _json_ready(rebuilt.get("feature_transform_contract")) != _json_ready(
        training.get("feature_transform_contract")
    ):
        raise RecommendationProvenanceError(
            "training lineage readback transform contract mismatch"
        )
    candidate_p1_values = [
        candidate_identity.get("training_source_hash"),
        candidate_identity.get("training_pit_hash"),
        candidate_identity.get("feature_transform_contract_hash"),
    ]
    candidate_p1_any = any(value not in (None, "") for value in candidate_p1_values)
    if candidate_p1_any and not all(value not in (None, "") for value in candidate_p1_values):
        raise RecommendationProvenanceError(
            "candidate training provenance declarations are incomplete"
        )
    if candidate_p1_any:
        expected_candidate_p1 = {
            "training_source_hash": rebuilt.get("training_source_hash"),
            "training_pit_hash": rebuilt.get("training_pit_hash"),
            "feature_transform_contract_hash": rebuilt.get(
                "feature_transform_contract_hash"
            ),
        }
        for key, expected in expected_candidate_p1.items():
            if candidate_identity.get(key) != expected:
                raise RecommendationProvenanceError(
                    f"candidate training provenance mismatch: {key}"
                )


def _validate_candidate_identity(candidate: Mapping[str, Any]) -> None:
    """Validate candidate identity hashes and, when available, its package."""

    for key in (
        "candidate_manifest_hash",
        "candidate_artifact_hash",
        "candidate_freeze_hash",
        "dataset_hash",
        "cost_scenario_hash",
    ):
        value = candidate.get(key)
        if value not in (None, ""):
            _require_hash(str(value), f"candidate {key}")
    root_text = str(candidate.get("candidate_root") or "").strip()
    if not root_text:
        return
    root = Path(root_text).expanduser().resolve()
    if root.is_symlink() or not root.is_dir():
        raise RecommendationProvenanceError("candidate package is missing or symlinked")
    candidate_path = root / "candidate.json"
    manifest_path = root / "manifest.json"
    if (
        candidate_path.is_symlink()
        or manifest_path.is_symlink()
        or not candidate_path.is_file()
        or not manifest_path.is_file()
    ):
        raise RecommendationProvenanceError("candidate package identity files are invalid")
    try:
        candidate_payload = json.loads(candidate_path.read_text(encoding="utf-8"))
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecommendationProvenanceError("candidate package identity is unreadable") from exc
    if not isinstance(candidate_payload, Mapping) or not isinstance(manifest_payload, Mapping):
        raise RecommendationProvenanceError("candidate package identity is invalid")
    candidate_id = str(candidate.get("candidate_id") or "")
    if str(candidate_payload.get("candidate_id") or "") != candidate_id:
        raise RecommendationProvenanceError("candidate package candidate identity mismatch")
    for key in ("dataset_hash", "cost_scenario_hash"):
        identity_value = candidate.get(key)
        package_value = candidate_payload.get(key)
        if identity_value not in (None, "") and package_value not in (None, ""):
            if str(identity_value) != str(package_value):
                raise RecommendationProvenanceError(
                    f"candidate package {key} mismatch"
                )
    manifest_hash = str(manifest_payload.get("manifest_hash") or "")
    _require_hash(manifest_hash, "candidate manifest hash")
    manifest_body = {
        key: value for key, value in manifest_payload.items() if key != "manifest_hash"
    }
    if manifest_hash != _hash_payload(manifest_body):
        raise RecommendationProvenanceError("candidate manifest self-hash mismatch")
    artifact_hash = str(manifest_payload.get("artifact_hash") or "")
    _require_hash(artifact_hash, "candidate artifact hash")
    artifact_name = str(manifest_payload.get("artifact_filename") or "")
    if (
        not artifact_name
        or Path(artifact_name).name != artifact_name
        or artifact_name in {".", ".."}
    ):
        raise RecommendationProvenanceError("candidate artifact filename is invalid")
    artifact_path = root / artifact_name
    if artifact_path.is_symlink() or not artifact_path.is_file() or _sha256_file(artifact_path) != artifact_hash:
        raise RecommendationProvenanceError("candidate artifact hash mismatch")
    for identity_key, package_key, expected in (
        ("candidate_manifest_hash", "manifest_hash", manifest_hash),
        ("candidate_artifact_hash", "artifact_hash", artifact_hash),
    ):
        identity_value = candidate.get(identity_key)
        package_value = candidate_payload.get(package_key)
        if identity_value not in (None, "") and str(identity_value) != expected:
            raise RecommendationProvenanceError(
                f"candidate identity {identity_key} mismatch"
            )
        if package_value not in (None, "") and str(package_value) != expected:
            raise RecommendationProvenanceError(
                f"candidate package {package_key} mismatch"
            )
    freeze_hash = str(candidate_payload.get("candidate_freeze_hash") or "")
    if freeze_hash:
        _require_hash(freeze_hash, "candidate freeze hash")
        try:
            from ml_module.recommendation_calibration_training import candidate_freeze_hash

            evaluation_payload = candidate_payload.get("evaluation")
            evaluation = (
                cast(Mapping[str, Any], evaluation_payload)
                if isinstance(evaluation_payload, Mapping)
                else {}
            )
            expected_freeze = candidate_freeze_hash(
                candidate_id=candidate_id,
                dataset_hash=str(candidate_payload.get("dataset_hash") or ""),
                manifest_hash=manifest_hash,
                artifact_hash=artifact_hash,
                evaluation=evaluation,
            )
        except Exception as exc:  # noqa: BLE001 - candidate identity must fail closed
            raise RecommendationProvenanceError("candidate freeze identity is invalid") from exc
        if freeze_hash != expected_freeze:
            raise RecommendationProvenanceError("candidate freeze hash mismatch")
        identity_freeze = candidate.get("candidate_freeze_hash")
        if identity_freeze not in (None, "") and str(identity_freeze) != freeze_hash:
            raise RecommendationProvenanceError("candidate identity freeze hash mismatch")


def _canonical_feature_schema(value: Sequence[Sequence[str]]) -> tuple[tuple[str, str, str], ...]:
    try:
        schema = tuple(tuple(str(item) for item in row) for row in value)
    except TypeError as exc:
        raise RecommendationProvenanceError("feature schema is not iterable") from exc
    if not schema or any(len(row) != 3 or not all(row) for row in schema):
        raise RecommendationProvenanceError("feature schema is invalid")
    if len({row[0] for row in schema}) != len(schema):
        raise RecommendationProvenanceError("feature schema ids are duplicated")
    return cast(tuple[tuple[str, str, str], ...], schema)


def _feature_schema_hash(schema: Sequence[Sequence[str]]) -> str:
    return _hash_payload({"feature_schema": [list(item) for item in schema]})


def _contract_hash(contract: Any) -> str | None:
    return str(contract.get("contract_hash") or "") if isinstance(contract, Mapping) else None


def _contract_id(contract: Any) -> str | None:
    return str(contract.get("contract_id") or "") if isinstance(contract, Mapping) else None


def _optional_hash(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    _require_hash(str(value), "hash")
    return str(value)


def _require_hash(value: str, field_name: str) -> None:
    if not value.startswith("sha256:") or len(value) != len("sha256:") + 64:
        raise RecommendationProvenanceError(f"{field_name} must be sha256")
    if any(char not in "0123456789abcdef" for char in value.split(":", 1)[1]):
        raise RecommendationProvenanceError(f"{field_name} must be lowercase sha256")


def _date_text(value: Any, field_name: str) -> str:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except (TypeError, ValueError) as exc:
        raise RecommendationProvenanceError(f"{field_name} is not ISO date") from exc


def _value(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _json_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RecommendationProvenanceError("provenance mapping is not an object")
    normalized = _json_ready(dict(value))
    if not isinstance(normalized, dict):
        raise RecommendationProvenanceError("provenance mapping normalization failed")
    return normalized


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _json_ready(asdict(cast(Any, value)))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_ready(item) for item in value]
    # Decimal and other exact numeric wrappers must be represented as text;
    # this provenance layer must not introduce financial float arithmetic.
    if hasattr(value, "as_tuple") and hasattr(value, "quantize"):
        return str(value)
    return str(value)


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(_json_ready(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _write_create_only(path: Path, payload: bytes) -> None:
    path = path.resolve()
    if path.is_symlink():
        raise RecommendationProvenanceError("immutable receipt destination is symlinked")
    if path.is_file():
        if path.read_bytes() != payload:
            raise RecommendationProvenanceError("immutable receipt conflict")
        return
    if path.exists():
        raise RecommendationProvenanceError("immutable receipt destination is not a file")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem[:24]}-", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    descriptor_open = True
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor_open = False
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise RecommendationProvenanceError("immutable receipt conflict after race")
    except OSError as exc:
        raise RecommendationProvenanceError("immutable receipt publication failed") from exc
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
        except OSError as exc:
            raise RecommendationProvenanceError("immutable receipt temporary cleanup failed") from exc


def _safe_component(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in value)
    return safe.strip("-._") or "unknown"
