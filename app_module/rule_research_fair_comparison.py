"""Read-only, research-only comparison of pinned UX21 labels and ML outputs.

The bundle binding is a post-hoc export envelope.  It must never be copied into
an inference request: each prediction retains the decision-time source hash
that was paired with its own canonical feature snapshot.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Sequence, cast

from app_module.rule_research_forward_store import read_forward_receipt
from app_module.rule_research_label_readiness import build_label_readiness_batch
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.historical_contracts import HistoricalFeatureRow
from ml_module.historical_feature_builder import HistoricalFeatureBuilder
from ml_module.historical_evaluation import (
    evaluate_historical_predictions,
    evaluate_return_predictions,
)
from ml_module.inference_contracts import (
    ShadowInferenceRequest,
    ShadowPredictionIdentity,
    prediction_id_for,
)
from ml_module.model_prediction_registries import MLModelRecord, MLShadowPredictionRecord


COMPARISON_SCHEMA = "rule-research-fair-comparison-policy.v1"
BUNDLE_SCHEMA = "rule-research-fair-inputs.v1"
REPORT_SCHEMA = "rule-research-fair-comparison.v1"
MAX_RECEIPTS = 32
MAX_ROWS = 4096
MAX_BYTES = 2 * 1024 * 1024
_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_COMPARISON_KEYS = {
    "schema_version", "policy_id", "version", "method_id", "horizon",
    "metrics", "top_k", "downside_threshold_bp",
}
_TARGET_KEYS = {
    "label_policy_sha256", "label_schema_sha256", "measure", "horizon",
    "downside_threshold_bp", "cost_policy_sha256", "benchmark_sha256",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _bundle_digest(bundle: dict[str, Any]) -> str:
    """Hash a canonical copy whose unordered sample collections have stable order."""
    normalized = dict(bundle)
    features = normalized.get("features")
    if isinstance(features, list):
        normalized["features"] = sorted(
            features, key=lambda item: item.get("sample_id", "") if isinstance(item, dict) else "",
        )
    for role_name in ("baseline", "candidate"):
        role = normalized.get(role_name)
        if isinstance(role, dict) and isinstance(role.get("predictions"), list):
            role_copy = dict(role)
            role_copy["predictions"] = sorted(
                role_copy["predictions"],
                key=lambda item: item.get("sample_id", "") if isinstance(item, dict) else "",
            )
            normalized[role_name] = role_copy
    return _sha256(normalized)


def _raw_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _hex_sha(value: object, field: str, *, required_prefix: bool = False) -> str:
    if (not isinstance(value, str) or not _SHA256.fullmatch(value)
            or (required_prefix and not value.startswith("sha256:"))):
        raise ValueError(f"{field}_sha256_invalid")
    return value


def _text(value: object, field: str, *, maximum: int = 256) -> str:
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value) > maximum):
        raise ValueError(f"{field}_invalid")
    return value


def _dto_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_invalid")
    return value


def _iso_date(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field}_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field}_invalid") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{field}_invalid")
    return value


def _identity_matches(report: dict[str, Any]) -> bool:
    identity = report.get("report_identity_sha256")
    if not isinstance(identity, str) or not _SHA256.fullmatch(identity):
        return False
    unsigned = {key: value for key, value in report.items() if key != "report_identity_sha256"}
    raw_identity = hashlib.sha256(_canonical(unsigned).encode("utf-8")).hexdigest()
    return identity.removeprefix("sha256:") == raw_identity


def _normalize_comparison_policy(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != _COMPARISON_KEYS:
        raise ValueError("comparison_policy_schema_invalid")
    if value["schema_version"] != COMPARISON_SCHEMA:
        raise ValueError("comparison_policy_version_unsupported")
    normalized: dict[str, Any] = {
        "schema_version": COMPARISON_SCHEMA,
        "policy_id": _text(value["policy_id"], "comparison_policy_id"),
        "version": _text(value["version"], "comparison_policy_version"),
        "method_id": _text(value["method_id"], "comparison_method_id"),
    }
    horizon = value["horizon"]
    if type(horizon) is not int or horizon not in {5, 10, 20}:
        raise ValueError("comparison_horizon_invalid")
    normalized["horizon"] = horizon
    metrics = value["metrics"]
    if not isinstance(metrics, str) or metrics not in {"return_only", "return_and_downside"}:
        raise ValueError("comparison_metrics_invalid")
    normalized["metrics"] = metrics
    top_k = value["top_k"]
    if type(top_k) is not int or top_k <= 0:
        raise ValueError("comparison_top_k_invalid")
    normalized["top_k"] = top_k
    threshold = value["downside_threshold_bp"]
    if metrics == "return_only":
        if threshold is not None:
            raise ValueError("comparison_return_only_threshold_must_be_null")
    elif type(threshold) is not int:
        raise ValueError("comparison_downside_threshold_required")
    normalized["downside_threshold_bp"] = threshold
    return normalized


def _feature_contract() -> tuple[str, str]:
    builder = HistoricalFeatureBuilder()
    return builder.load_contract.registry_hash, builder.load_contract.schema_hash


def comparison_binding(report: dict[str, Any], policy: dict[str, Any]) -> str:
    """Return the SHA-256 post-hoc bundle binding for this label report/policy."""
    if not isinstance(report, dict) or not _identity_matches(report):
        raise ValueError("label_report_identity_invalid")
    normalized = _normalize_comparison_policy(policy)
    if normalized is None:
        raise ValueError("comparison_policy_required_for_binding")
    registry_hash, schema_hash = _feature_contract()
    return _sha256({
        "label_report_identity_sha256": report["report_identity_sha256"],
        "comparison_policy": normalized,
        "feature_registry_hash": registry_hash,
        "feature_schema_hash": schema_hash,
    })


def _cost_semantics(receipts: list[dict[str, Any]]) -> dict[str, Any] | None:
    values = [item.get("cost_policy") for item in receipts]
    first = values[0] if values else None
    if any(_canonical(value) != _canonical(first) for value in values[1:]):
        raise ValueError("comparison_cost_policy_mixed")
    if first is None:
        return None
    if not isinstance(first, dict):
        raise ValueError("comparison_cost_policy_invalid")
    return first


def _benchmark_semantics(
    receipts: list[dict[str, Any]], cancel_callback: Callable[[], bool] | None = None,
) -> dict[str, Any] | None:
    """Read each sealed declaration; exclude endpoint-specific row pins."""
    normalized: list[dict[str, Any] | None] = []
    for item in receipts:
        if cancel_callback is not None and cancel_callback():
            raise _Cancelled
        parent_path = item.get("parent_receipt_path")
        outcome_path = item.get("outcome_receipt_path")
        if not isinstance(parent_path, str) or not isinstance(outcome_path, str):
            raise ValueError("comparison_benchmark_receipt_path_missing")
        readback = read_forward_receipt(parent_path, outcome_path, cancel_callback=cancel_callback)
        contract = readback.get("source_contract")
        if readback.get("cancelled"):
            raise _Cancelled
        if not isinstance(contract, dict):
            raise ValueError("comparison_benchmark_source_contract_missing")
        projection = readback.get("projection")
        if (readback.get("saved_identity_sha256") != item.get("outcome_identity_sha256")
                or readback.get("input_sha256") != item.get("outcome_capture_sha256")
                or not isinstance(projection, dict)
                or projection.get("parent_identity_sha256") != item.get("parent_identity_sha256")
                or _raw_sha256(contract) != item.get("source_contract_sha256")):
            raise ValueError("comparison_benchmark_sealed_receipt_changed")
        request = contract.get("benchmark_request")
        projection = item.get("benchmark")
        if request is None:
            if projection is not None:
                raise ValueError("comparison_benchmark_declaration_projection_mismatch")
            normalized.append(None)
            continue
        if not isinstance(request, dict):
            raise ValueError("comparison_benchmark_request_invalid")
        keys = (
            "schema_version", "version", "source_identity", "benchmark_name",
            "currency", "unit", "price_basis", "corporate_action_basis",
            "target_currency", "target_price_basis", "target_corporate_action_basis",
        )
        if any(key not in request for key in keys):
            raise ValueError("comparison_benchmark_declaration_incomplete")
        declaration = {key: request[key] for key in keys}
        database = request.get("database_path")
        if not isinstance(database, str):
            raise ValueError("comparison_benchmark_database_identity_missing")
        declaration["database_path"] = str(Path(database).resolve())
        declaration["adapter_version"] = item.get("adapter_version")
        if projection is not None:
            if not isinstance(projection, dict):
                raise ValueError("comparison_benchmark_spec_invalid")
            expected = {
                "instrument_id": f"market_indices.{request['benchmark_name']}",
                "currency": request["currency"], "unit": request["unit"],
                "price_basis": request["price_basis"],
                "corporate_action_basis": request["corporate_action_basis"],
            }
            if any(projection.get(key) != value for key, value in expected.items()):
                raise ValueError("comparison_benchmark_declaration_projection_mismatch")
        normalized.append(declaration)
    if cancel_callback is not None and cancel_callback():
        raise _Cancelled
    first = normalized[0] if normalized else None
    if any(_canonical(value) != _canonical(first) for value in normalized[1:]):
        raise ValueError("comparison_benchmark_semantics_mixed")
    return first


def comparison_target_contract(
    report: dict[str, Any], policy: dict[str, Any],
    *, cancel_callback: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Expected per-model target semantics; callers must explicitly export it."""
    if not isinstance(report, dict) or not _identity_matches(report):
        raise ValueError("label_report_identity_invalid")
    normalized = _normalize_comparison_policy(policy)
    if normalized is None:
        raise ValueError("comparison_policy_required_for_target_contract")
    label_config = report.get("label_policy")
    if not isinstance(label_config, dict) or label_config.get("status") != "configured":
        raise ValueError("comparison_label_policy_required")
    label_policy = label_config.get("value")
    if not isinstance(label_policy, dict):
        raise ValueError("comparison_label_policy_invalid")
    if normalized["horizon"] not in label_config.get("value", {}).get("horizons", []):
        raise ValueError("comparison_horizon_not_in_label_policy")
    receipts = report.get("receipts")
    if not isinstance(receipts, list) or not receipts:
        raise ValueError("comparison_receipt_semantics_missing")
    cost = _cost_semantics(receipts)
    benchmark = _benchmark_semantics(receipts, cancel_callback)
    cost_hash = None if cost is None else _sha256(cost)
    benchmark_hash = None if benchmark is None else _sha256(benchmark)
    return {
        "label_policy_sha256": label_config.get("sha256"),
        "label_schema_sha256": label_config.get("label_schema_sha256"),
        "measure": label_policy.get("measure"),
        "horizon": normalized["horizon"],
        "downside_threshold_bp": normalized["downside_threshold_bp"],
        "cost_policy_sha256": cost_hash,
        "benchmark_sha256": benchmark_hash,
    }


def _cancelled() -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA,
        "status": "cancelled",
        "readiness": "cancelled",
        "reason_codes": ["cancelled"],
        "summary_text": "ML \u6bd4\u8f03\u5df2\u53d6\u6d88\uff1b\u6c92\u6709\u767c\u5e03\u90e8\u5206\u6bd4\u8f03\u7d50\u679c\uff0c\u53ef\u5b89\u5168\u91cd\u8a66。",
        "metric_scope": "pooled_common_samples_in_selected_evaluation_window",
        "common_cohort": {"sample_ids": [], "count": 0},
        "member_ledger": [],
        "baseline": None,
        "candidate": None,
        "metric_differences": None,
        "training_eligible": False,
        "historical_pit_eligible": False,
        "formal_eligible": False,
        "natural_authority": False,
        "execution_eligible": False,
        "production_blend_alpha_bp": 0,
        "selection_status": "unknown",
    }
    report["report_identity_sha256"] = _sha256(report)
    return report


def _read_source_semantics(
    receipts: Sequence[tuple[str | Path, str | Path]],
    label_report: dict[str, Any],
    cancel: Callable[[], bool],
) -> dict[str, Any]:
    summaries = label_report.get("receipts")
    if not isinstance(summaries, list) or len(summaries) != len(receipts):
        raise ValueError("comparison_receipt_summary_mismatch")
    by_outcome = {str(Path(outcome).resolve()): Path(parent).resolve()
                  for parent, outcome in receipts}
    source_rows: list[dict[str, Any]] = []
    for summary in summaries:
        if cancel():
            raise _Cancelled
        outcome_path = summary.get("outcome_receipt_path")
        parent_path = summary.get("parent_receipt_path")
        if (not isinstance(outcome_path, str) or not isinstance(parent_path, str)
                or by_outcome.get(str(Path(outcome_path).resolve())) != Path(parent_path).resolve()):
            raise ValueError("comparison_receipt_paths_do_not_match")
        readback = read_forward_receipt(parent_path, outcome_path, cancel_callback=cancel)
        if readback.get("cancelled"):
            raise _Cancelled
        projection = readback.get("projection")
        contract = readback.get("source_contract")
        if not isinstance(projection, dict) or not isinstance(contract, dict):
            raise ValueError("comparison_sealed_source_contract_missing")
        if (readback.get("saved_identity_sha256") != summary.get("outcome_identity_sha256")
                or readback.get("input_sha256") != summary.get("outcome_capture_sha256")
                or projection.get("parent_identity_sha256") != summary.get("parent_identity_sha256")):
            raise ValueError("comparison_sealed_receipt_identity_changed")
        contract_sha = _raw_sha256(contract)
        if contract_sha != summary.get("source_contract_sha256"):
            raise ValueError("comparison_sealed_source_contract_changed")
        database = contract.get("database")
        schema_identity = contract.get("schema_identity_sha256")
        if not isinstance(database, str) or not isinstance(schema_identity, str):
            raise ValueError("comparison_source_database_identity_missing")
        stable_source = {
            "adapter_version": contract.get("adapter_version"),
            "database": str(Path(database).resolve()),
            "schema_identity_sha256": schema_identity,
            "database_revision_pin": contract.get("database_revision_pin"),
            "calendar_cache": contract.get("calendar_cache"),
            "calendar_scope": contract.get("calendar_scope"),
            "temporary_closure_status": contract.get("temporary_closure_status"),
            "price_basis": contract.get("price_basis"),
            "corporate_action_basis": contract.get("corporate_action_basis"),
            "source_mode": contract.get("source_mode"),
            "source_availability": contract.get("source_availability"),
            "target_basis_status": contract.get("target_basis_status"),
        }
        source_rows.append({
            "parent_identity_sha256": summary.get("parent_identity_sha256"),
            "outcome_identity_sha256": summary.get("outcome_identity_sha256"),
            "outcome_capture_sha256": summary.get("outcome_capture_sha256"),
            "source_contract_sha256": contract_sha,
            "logical_source": stable_source,
            "logical_source_sha256": _sha256(stable_source),
            "adapter_version": stable_source["adapter_version"],
            "database": stable_source["database"],
            "schema_identity_sha256": schema_identity,
            "database_revision_pin": stable_source["database_revision_pin"],
            "source_mode": stable_source["source_mode"],
            "source_availability": stable_source["source_availability"],
            "target_basis_status": stable_source["target_basis_status"],
        })
    if cancel():
        raise _Cancelled
    canonical = [_canonical(item["logical_source"]) for item in source_rows]
    if canonical and any(item != canonical[0] for item in canonical[1:]):
        raise ValueError("comparison_logical_source_or_version_mixed")
    return {
        "status": "single_fixed_logical_source_version" if len(source_rows) == 1 else "same_fixed_logical_source_version",
        "receipt_pins": source_rows,
        "logical_source_sha256": source_rows[0]["logical_source_sha256"] if source_rows else None,
        "all_receipts_share_database_schema_adapter_revision_calendar_and_basis": True,
        "current_observed_availability_never_becomes_pit": True,
    }


class _Cancelled(Exception):
    pass


def _record_dict(value: object, field_name: str, expected_keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise ValueError(f"{field_name}_schema_invalid")
    return value


def _as_model(value: object, dataset_id: str) -> MLModelRecord:
    names = {field.name for field in fields(MLModelRecord)}
    raw = _record_dict(value, "model_record", names)
    for field_name in (
        "model_id", "dataset_id", "created_at", "model_family",
        "artifact_path", "artifact_hash", "lifecycle_status",
    ):
        _dto_text(raw[field_name], f"model_{field_name}")
    if raw["calibration_id"] is not None:
        _dto_text(raw["calibration_id"], "model_calibration_id")
    feature_names = raw["feature_names"]
    if not isinstance(feature_names, (tuple, list)) or any(not isinstance(name, str) for name in feature_names):
        raise ValueError("model_feature_names_invalid")
    model = MLModelRecord(**{**raw, "feature_names": tuple(feature_names)})
    if model.dataset_id != dataset_id:
        raise ValueError("comparison_model_dataset_mismatch")
    if model.feature_names != CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids:
        raise ValueError("comparison_model_feature_schema_mismatch")
    _hex_sha(model.artifact_hash, "model_artifact")
    if raw["shadow_only"] is not True or raw["production_eligible"] is not False:
        raise ValueError("comparison_model_qualification_invalid")
    return model


def _as_feature(value: object, label_row: dict[str, Any], source_hash: object) -> tuple[HistoricalFeatureRow, Any]:
    _hex_sha(source_hash, "feature_source_versions")
    raw = _record_dict(value, "historical_feature_row", {
        "symbol", "decision_date", "feature_as_of_date", "available_date", "values",
    })
    values = raw["values"]
    if not isinstance(values, (list, tuple)):
        raise ValueError("historical_feature_values_invalid")
    pairs: list[tuple[str, int | None]] = []
    for pair in values:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2 or not isinstance(pair[0], str):
            raise ValueError("historical_feature_value_pair_invalid")
        if pair[1] is not None and type(pair[1]) is not int:
            raise ValueError("historical_feature_value_not_integer_or_null")
        pairs.append((pair[0], pair[1]))
    feature = HistoricalFeatureRow(
        symbol=_dto_text(raw["symbol"], "feature_symbol"), decision_date=_iso_date(raw["decision_date"], "feature_decision_date"),
        feature_as_of_date=_iso_date(raw["feature_as_of_date"], "feature_as_of_date"),
        available_date=_iso_date(raw["available_date"], "feature_available_date"), values=tuple(pairs),
    )
    if feature.symbol != label_row["stock_code"] or feature.decision_date != label_row["decision_date"]:
        raise ValueError("comparison_feature_sample_identity_mismatch")
    vector = HistoricalFeatureBuilder().load(feature)
    if feature.available_date >= feature.decision_date:
        raise ValueError("comparison_feature_availability_must_precede_decision")
    return feature, vector


def _role_payload(value: object, role: str, dataset_id: str, expected_target: dict[str, Any],
                  split: dict[str, Any], label_rows: dict[str, dict[str, Any]],
                  vectors: dict[str, Any], feature_source_hashes: dict[str, str],
                  source_hash_formats: set[str]) -> dict[str, Any]:
    required_role_keys = {"model_record", "training_audit", "predictions"}
    if not isinstance(value, dict) or not required_role_keys <= set(value) or set(value) - (required_role_keys | {"target_contract"}):
        raise ValueError(f"{role}_role_schema_invalid")
    model = _as_model(value["model_record"], dataset_id)
    target_value = value.get("target_contract")
    target_is_valid = isinstance(target_value, dict) and set(target_value) == _TARGET_KEYS
    target_matches = bool(target_is_valid and target_value == expected_target)
    target = dict(target_value) if isinstance(target_value, dict) and target_is_valid else None
    audit = _record_dict(value["training_audit"], f"{role}_training_audit", {
        "training_as_of", "max_train_decision_date", "max_train_label_available_date",
    })
    training_as_of = _iso_date(audit["training_as_of"], f"{role}_training_as_of")
    max_decision = _iso_date(audit["max_train_decision_date"], f"{role}_max_train_decision_date")
    max_label_available = _iso_date(audit["max_train_label_available_date"], f"{role}_max_train_label_available_date")
    if (training_as_of != split["training_as_of"]
            or not split["train_start"] <= max_decision <= split["train_end"]
            or max_decision > training_as_of
            or max_label_available <= max_decision
            or max_label_available > training_as_of
            or training_as_of >= split["evaluation_start"]):
        raise ValueError(f"{role}_training_audit_temporal_mismatch")
    raw_predictions = value["predictions"]
    if not isinstance(raw_predictions, list) or len(raw_predictions) > MAX_ROWS:
        raise ValueError(f"{role}_predictions_bound")
    prediction_rows: dict[str, dict[str, Any]] = {}
    prediction_ids: set[str] = set()
    record_keys = {field.name for field in fields(MLShadowPredictionRecord)}
    for entry in raw_predictions:
        if not isinstance(entry, dict) or set(entry) != {"sample_id", "record"}:
            raise ValueError(f"{role}_prediction_entry_invalid")
        sample_id = _text(entry["sample_id"], f"{role}_prediction_sample_id", maximum=64)
        if sample_id not in label_rows:
            raise ValueError(f"{role}_prediction_sample_id_unknown")
        if sample_id in prediction_rows:
            raise ValueError(f"{role}_duplicate_prediction_sample_id")
        raw = _record_dict(entry["record"], f"{role}_prediction_record", record_keys)
        for field_name in (
            "prediction_id", "model_id", "dataset_id", "symbol",
            "decision_date", "available_date", "feature_snapshot_hash",
            "source_versions_hash",
        ):
            _dto_text(raw[field_name], f"{role}_prediction_{field_name}")
        numeric = ("return_prediction_bp", "ranking_score", "downside_probability", "uncertainty_bp")
        if any(type(raw[field]) is not int for field in numeric):
            raise ValueError(f"{role}_prediction_values_must_be_integer_bp")
        record = MLShadowPredictionRecord(**raw)
        _iso_date(record.decision_date, f"{role}_prediction_decision_date")
        _iso_date(record.available_date, f"{role}_prediction_available_date")
        if (record.model_id != model.model_id or record.dataset_id != dataset_id
                or record.available_date > record.decision_date):
            raise ValueError(f"{role}_prediction_model_or_time_binding_mismatch")
        if record.prediction_id in prediction_ids:
            raise ValueError(f"{role}_duplicate_prediction_identity")
        prediction_ids.add(record.prediction_id)
        label_row = label_rows[sample_id]
        feature_hash = feature_source_hashes.get(sample_id)
        vector = vectors.get(sample_id)
        if (record.symbol != label_row["stock_code"]
                or record.decision_date != label_row["decision_date"]
                or (vector is not None and record.feature_snapshot_hash != vector.snapshot_hash)
                or (feature_hash is not None and record.source_versions_hash != feature_hash)):
            raise ValueError(f"{role}_prediction_feature_source_binding_mismatch")
        if raw["shadow_only"] is not True or raw["production_action_allowed"] is not False:
            raise ValueError(f"{role}_prediction_qualification_invalid")
        _hex_sha(record.feature_snapshot_hash, f"{role}_feature_snapshot", required_prefix=True)
        _hex_sha(record.source_versions_hash, f"{role}_source_versions")
        source_hash_formats.add("prefixed" if record.source_versions_hash.startswith("sha256:") else "raw")
        if vector is not None:
            request = ShadowInferenceRequest(
                model_id=model.model_id, dataset_id=dataset_id,
                decision_date=record.decision_date,
                feature_snapshot_hash=record.feature_snapshot_hash,
                feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
                source_versions={"decision_feature_source": record.source_versions_hash},
                feature_max_available_date=vector.available_date,
            )
            if prediction_id_for(request, record.symbol) != record.prediction_id:
                raise ValueError(f"{role}_prediction_id_mismatch")
        identity = ShadowPredictionIdentity(
            prediction_id=record.prediction_id, symbol=record.symbol,
            return_prediction_bp=cast(int, record.return_prediction_bp),
            ranking_score_bp=cast(int, record.ranking_score),
            downside_probability_bp=cast(int, record.downside_probability),
            uncertainty_bp=record.uncertainty_bp,
        )
        prediction_rows[sample_id] = {
            "record": record,
            "identity": identity,
        }
    return {
        "model": model,
        "training_audit": dict(audit),
        "target_contract": target,
        "target_contract_matches": target_matches,
        "predictions": prediction_rows,
    }


def _model_pin(role: dict[str, Any]) -> dict[str, Any]:
    model: MLModelRecord = role["model"]
    return {
        "model_id": model.model_id,
        "dataset_id": model.dataset_id,
        "created_at": model.created_at,
        "model_family": model.model_family,
        "feature_names": list(model.feature_names),
        "artifact_path": model.artifact_path,
        "artifact_hash": model.artifact_hash,
        "calibration_id": model.calibration_id,
        "lifecycle_status": model.lifecycle_status,
        "shadow_only": model.shadow_only,
        "production_eligible": model.production_eligible,
        "training_audit": role["training_audit"],
        "target_contract": role["target_contract"],
    }


def _prediction_pin(prediction: dict[str, Any] | None) -> dict[str, Any] | None:
    if prediction is None:
        return None
    record: MLShadowPredictionRecord = prediction["record"]
    return {
        "prediction_id": record.prediction_id,
        "model_id": record.model_id,
        "dataset_id": record.dataset_id,
        "symbol": record.symbol,
        "decision_date": record.decision_date,
        "available_date": record.available_date,
        "return_prediction_bp": record.return_prediction_bp,
        "ranking_score": record.ranking_score,
        "downside_probability": record.downside_probability,
        "uncertainty_bp": record.uncertainty_bp,
        "feature_snapshot_hash": record.feature_snapshot_hash,
        "source_versions_hash": record.source_versions_hash,
        "shadow_only": record.shadow_only,
        "production_action_allowed": record.production_action_allowed,
    }


def _role_metrics(role: dict[str, Any], common_ids: list[str], rows: dict[str, dict[str, Any]],
                  policy: dict[str, Any]) -> dict[str, int] | None:
    targets = [rows[sample_id]["value_bp"] for sample_id in common_ids]
    predictions = [role["predictions"][sample_id]["record"] for sample_id in common_ids]
    if policy["metrics"] == "return_only":
        return evaluate_return_predictions(
            return_targets_bp=targets,
            return_predictions_bp=[item.return_prediction_bp for item in predictions],
            ranking_scores=[item.ranking_score for item in predictions],
            top_k=policy["top_k"],
        )
    threshold = policy["downside_threshold_bp"]
    downside_targets = [int(value <= threshold) for value in targets]
    return evaluate_historical_predictions(
        return_targets_bp=targets,
        downside_targets=downside_targets,
        return_predictions_bp=[item.return_prediction_bp for item in predictions],
        ranking_scores=[item.ranking_score for item in predictions],
        downside_probabilities_bp=[item.downside_probability for item in predictions],
        top_k=policy["top_k"],
    )


def _base_report(label_report: dict[str, Any], policy: dict[str, Any] | None,
                 split_policy: dict[str, Any] | None,
                 comparison_policy: dict[str, Any] | None) -> dict[str, Any]:
    label_config = label_report.get("label_policy", {})
    split_config = label_report.get("split_policy", {})
    label_value = label_config.get("value") if isinstance(label_config, dict) else None
    return {
        "schema_version": REPORT_SCHEMA,
        "status": "blocked_missing_configuration",
        "readiness": "blocked_missing_configuration",
        "reason_codes": [],
        "summary_text": "",
        "label_readiness_identity_sha256": label_report.get("report_identity_sha256"),
        "label_policy": label_value,
        "label_policy_sha256": label_config.get("sha256") if isinstance(label_config, dict) else None,
        "label_schema_sha256": label_config.get("label_schema_sha256") if isinstance(label_config, dict) else None,
        "split_policy": split_config.get("value") if isinstance(split_config, dict) else None,
        "split_policy_sha256": split_config.get("sha256") if isinstance(split_config, dict) else None,
        "comparison_policy": comparison_policy,
        "comparison_policy_sha256": None if comparison_policy is None else _sha256(comparison_policy),
        "comparison_binding_sha256": None,
        "method_id": None if comparison_policy is None else comparison_policy["method_id"],
        "horizon": None if comparison_policy is None else comparison_policy["horizon"],
        "measure": label_value.get("measure") if isinstance(label_value, dict) else None,
        "metrics_policy": None if comparison_policy is None else comparison_policy["metrics"],
        "top_k": None if comparison_policy is None else comparison_policy["top_k"],
        "downside_threshold_bp": None if comparison_policy is None else comparison_policy["downside_threshold_bp"],
        "source_denominators": label_report.get("source_denominators", {}),
        "label_denominators": label_report.get("label_denominators", {}),
        "prior_baseline_readiness": label_report.get("baseline_readiness"),
        "source_pins": label_report.get("receipts", []),
        "source_semantics": None,
        "cohort_denominators": {},
        "metric_interpretation": {
            "mae_bp": "lower_is_better",
            "brier_bp": "lower_is_better",
            "precision_at_k_bp": "higher_is_better",
            "ndcg_bp": "higher_is_better",
            "bucket_monotonicity_bp": "higher_is_better",
            "coverage_bp": "common_cohort_only_not_full_population_coverage",
        },
        "common_cohort": {"sample_ids": [], "count": 0},
        "member_ledger": [],
        "baseline": None,
        "candidate": None,
        "metric_differences": None,
        "metric_scope": "pooled_common_samples_in_selected_evaluation_window",
        "top_k_semantics": "研究樣本內 pooled ranking；不是每日交易選股或execution selection",
        "training_eligible": False,
        "historical_pit_eligible": False,
        "formal_eligible": False,
        "natural_authority": False,
        "execution_eligible": False,
        "production_blend_alpha_bp": 0,
        "selection_status": "unknown",
    }


def _seal_report(report: dict[str, Any]) -> dict[str, Any]:
    report["report_identity_sha256"] = _sha256(report)
    size = len(_canonical(report).encode("utf-8"))
    if size > MAX_BYTES:
        raise ValueError("fair_comparison_report_byte_bound")
    return report


def build_fair_comparison(
    receipts: Sequence[tuple[str | Path, str | Path]],
    label_policy: dict[str, Any] | None,
    split_policy: dict[str, Any] | None,
    comparison_policy: dict[str, Any] | None = None,
    bundle: dict[str, Any] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Compare two exported shadow roles on exactly the same sealed label rows.

    This function reads sealed receipts and in-memory JSON-shaped inputs.  It
    never writes registries, trains or loads models, or modifies receipts.
    """
    cancel = cancel_callback or (lambda: False)
    if cancel():
        return _cancelled()
    if not isinstance(receipts, Sequence) or isinstance(receipts, (str, bytes)):
        raise ValueError("fair_receipts_sequence_required")
    if not 1 <= len(receipts) <= MAX_RECEIPTS:
        raise ValueError("fair_receipt_count_bound")
    label_report = build_label_readiness_batch(
        receipts, label_policy, split_policy, cancel_callback=cancel,
    )
    if label_report.get("status") == "cancelled" or cancel():
        return _cancelled()
    normalized_comparison = _normalize_comparison_policy(comparison_policy)
    report = _base_report(label_report, label_policy, split_policy, normalized_comparison)
    if normalized_comparison is None:
        report["reason_codes"] = ["comparison_policy_not_configured"]
    else:
        report["comparison_binding_sha256"] = comparison_binding(label_report, normalized_comparison)
        if label_report.get("label_policy", {}).get("status") != "configured":
            report["reason_codes"].append("label_policy_not_configured")
        elif normalized_comparison["horizon"] not in label_report["label_policy"].get("horizons", []):
            raise ValueError("comparison_horizon_not_in_label_policy")
        if label_report.get("split_policy", {}).get("status") == "not_configured":
            report["reason_codes"].append("split_policy_not_configured")
    if report["reason_codes"]:
        report["summary_text"] = _summary(report)
        return _seal_report(report)
    assert normalized_comparison is not None
    if cancel():
        return _cancelled()
    try:
        report["source_semantics"] = _read_source_semantics(receipts, label_report, cancel)
    except _Cancelled:
        return _cancelled()
    if cancel():
        return _cancelled()
    try:
        target_contract = comparison_target_contract(
            label_report, normalized_comparison, cancel_callback=cancel,
        )
    except _Cancelled:
        return _cancelled()
    report["expected_target_contract"] = target_contract
    label_rows = label_report.get("label_rows")
    if not isinstance(label_rows, list) or len(label_rows) > MAX_ROWS:
        raise ValueError("fair_label_row_bound")
    selected = [row for row in label_rows
                if row.get("method_id") == normalized_comparison["method_id"]
                and row.get("horizon") == f"H{normalized_comparison['horizon']}"]
    if len(selected) > MAX_ROWS:
        raise ValueError("fair_selected_row_bound")
    selected.sort(key=lambda row: (row.get("decision_date", ""), row.get("stock_code", ""), row.get("sample_id", "")))
    rows_by_id = {row["sample_id"]: row for row in selected}
    if len(rows_by_id) != len(selected):
        raise ValueError("fair_duplicate_selected_sample_id")
    report["cohort_denominators"] = {
        "parent_member_rows": label_report.get("source_denominators", {}).get("represented_denominator_sum", 0),
        "method_member_rows": label_report.get("source_denominators", {}).get("method_member_rows", 0),
        "included_parent_population_rows": label_report.get("source_denominators", {}).get("included_denominator_sum", 0),
        "selected_method_horizon_members": len(selected),
        "member_state_counts": {
            state: sum(row.get("member_state") == state for row in selected)
            for state in ("matched", "notmatched", "excluded", "unknown", "uncaptured")
        },
        "evaluation_window_rows": sum(row.get("split_role") == "evaluation_window_research_only" for row in selected),
        "non_evaluation_rows": sum(row.get("split_role") != "evaluation_window_research_only" for row in selected),
        "evaluation_value_rows": sum(row.get("split_role") == "evaluation_window_research_only"
                                      and type(row.get("value_bp")) is int for row in selected),
        "missing_or_unqualified_label_rows": sum(row.get("value_bp") is None for row in selected),
        "availability_unknown_rows": sum(row.get("availability_status") == "unknown" for row in selected),
        "availability_invalid_rows": sum(row.get("availability_status") == "invalid" for row in selected),
        "matched_controls_in_denominator": sum(row.get("member_state") == "notmatched" for row in selected),
        "selection_status": "unknown",
    }
    if not selected:
        report["reason_codes"] = ["selected_method_horizon_has_no_members"]

    bundle_digest: str | None = None
    baseline_role: dict[str, Any] | None = None
    candidate_role: dict[str, Any] | None = None
    feature_vectors: dict[str, Any] = {}
    feature_sources: dict[str, str] = {}
    feature_rows: dict[str, HistoricalFeatureRow] = {}
    if bundle is None:
        report["reason_codes"].append("fair_inputs_bundle_missing")
    else:
        try:
            bundle_bytes = _canonical(bundle).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise ValueError("fair_inputs_bundle_not_json_serializable") from error
        if len(bundle_bytes) > MAX_BYTES:
            raise ValueError("fair_inputs_bundle_byte_bound")
        if not isinstance(bundle, dict) or set(bundle) != {
            "schema_version", "version", "binding_sha256", "dataset_id",
            "feature_registry_hash", "feature_schema_hash", "features", "baseline", "candidate",
        }:
            raise ValueError("fair_inputs_bundle_schema_invalid")
        if bundle["schema_version"] != BUNDLE_SCHEMA or bundle["version"] != "1":
            raise ValueError("fair_inputs_bundle_version_unsupported")
        _text(bundle["dataset_id"], "fair_bundle_dataset_id")
        expected_binding = comparison_binding(label_report, normalized_comparison)
        if _hex_sha(bundle["binding_sha256"], "fair_bundle_binding", required_prefix=True) != expected_binding:
            raise ValueError("fair_bundle_binding_mismatch")
        registry_hash, schema_hash = _feature_contract()
        if bundle["feature_registry_hash"] != registry_hash or bundle["feature_schema_hash"] != schema_hash:
            raise ValueError("fair_bundle_feature_contract_mismatch")
        if not isinstance(bundle["features"], list) or len(bundle["features"]) > MAX_ROWS:
            raise ValueError("fair_feature_row_bound")
        source_formats: set[str] = set()
        for entry in bundle["features"]:
            if not isinstance(entry, dict) or set(entry) != {"sample_id", "source_versions_hash", "feature"}:
                raise ValueError("fair_feature_entry_invalid")
            sample_id = _text(entry["sample_id"], "fair_feature_sample_id", maximum=64)
            if sample_id not in rows_by_id:
                raise ValueError("fair_feature_sample_id_unknown")
            if sample_id in feature_rows:
                raise ValueError("fair_duplicate_feature_sample_id")
            raw_source_hash = _hex_sha(entry["source_versions_hash"], "fair_feature_source_versions")
            source_formats.add("prefixed" if raw_source_hash.startswith("sha256:") else "raw")
            feature, vector = _as_feature(entry["feature"], rows_by_id[sample_id], raw_source_hash)
            feature_rows[sample_id] = feature
            feature_vectors[sample_id] = vector
            feature_sources[sample_id] = raw_source_hash
        bundle_digest = _bundle_digest(bundle)
        try:
            expected_target = comparison_target_contract(
                label_report, normalized_comparison, cancel_callback=cancel,
            )
            baseline_role = None if bundle["baseline"] is None else _role_payload(
                bundle["baseline"], "baseline", bundle["dataset_id"], expected_target,
                label_report["split_policy"]["value"], rows_by_id, feature_vectors, feature_sources, source_formats)
            candidate_role = None if bundle["candidate"] is None else _role_payload(
                bundle["candidate"], "candidate", bundle["dataset_id"], expected_target,
                label_report["split_policy"]["value"], rows_by_id, feature_vectors, feature_sources, source_formats)
        except _Cancelled:
            return _cancelled()
        report["bundle_identity_sha256"] = bundle_digest
        report["bundle_pins"] = {
            "binding_sha256": bundle["binding_sha256"],
            "bundle_identity_sha256": bundle_digest,
            "dataset_id": bundle["dataset_id"],
            "feature_registry_hash": bundle["feature_registry_hash"],
            "feature_schema_hash": bundle["feature_schema_hash"],
            "feature_row_count": len(feature_rows),
            "feature_and_prediction_source_hash_formats": sorted(source_formats),
        }
    if cancel():
        return _cancelled()

    ledger: list[dict[str, Any]] = []
    common_ids: list[str] = []
    for row in selected:
        if cancel():
            return _cancelled()
        sample_id = row["sample_id"]
        reasons: list[str] = []
        if row.get("split_role") != "evaluation_window_research_only":
            reasons.append("outside_evaluation_window")
        if row.get("member_state") == "excluded":
            reasons.append("member_excluded_by_parent_receipt")
        elif row.get("member_state") in {"unknown", "uncaptured"}:
            reasons.append(f"member_state_{row['member_state']}")
        if type(row.get("value_bp")) is not int:
            reasons.extend(row.get("reason_codes", []) or ["label_value_missing_or_unqualified"])
        if row.get("availability_status") == "invalid":
            reasons.append("label_availability_invalid")
        vector = feature_vectors.get(sample_id)
        if sample_id not in feature_rows:
            reasons.append("feature_row_missing")
        elif vector is not None and vector.missing_feature_ids:
            reasons.extend(f"feature_value_missing:{name}" for name in vector.missing_feature_ids)
        baseline_prediction = None if baseline_role is None else baseline_role["predictions"].get(sample_id)
        candidate_prediction = None if candidate_role is None else candidate_role["predictions"].get(sample_id)
        if baseline_role is None:
            reasons.append("baseline_role_missing")
        elif baseline_prediction is None:
            reasons.append("baseline_prediction_missing")
        if candidate_role is None:
            reasons.append("candidate_role_missing")
        elif candidate_prediction is None:
            reasons.append("candidate_prediction_missing")
        if baseline_role is not None and not baseline_role["target_contract_matches"]:
            reasons.append("baseline_target_contract_incompatible")
        if candidate_role is not None and not candidate_role["target_contract_matches"]:
            reasons.append("candidate_target_contract_incompatible")
        if row.get("availability_status") == "unknown" and type(row.get("value_bp")) is int:
            research_limitations = ["retrospective_label_availability_unknown_research_only"]
        else:
            research_limitations = []
        valid_label = (type(row.get("value_bp")) is int
                       and row.get("availability_status") != "invalid")
        eligible_member = row.get("member_state") in {"matched", "notmatched"}
        has_complete_feature = vector is not None and not vector.missing_feature_ids
        has_both_predictions = baseline_prediction is not None and candidate_prediction is not None
        common = (
            row.get("split_role") == "evaluation_window_research_only"
            and valid_label and eligible_member and has_complete_feature and has_both_predictions
            and not (baseline_role is None or candidate_role is None)
            and baseline_role["target_contract_matches"] and candidate_role["target_contract_matches"]
        )
        if common:
            common_ids.append(sample_id)
        ledger.append({
            "sample_id": sample_id,
            "comparison_group_id": row.get("comparison_group_id"),
            "method_id": row.get("method_id"),
            "stock_code": row.get("stock_code"),
            "decision_date": row.get("decision_date"),
            "horizon": row.get("horizon"),
            "measure": row.get("measure"),
            "member_state": row.get("member_state"),
            "selection_status": "unknown",
            "split_role": row.get("split_role"),
            "label_value_bp": row.get("value_bp"),
            "label_end_date": row.get("label_end_date"),
            "available_date": row.get("available_date"),
            "availability_status": row.get("availability_status"),
            "label_reason_codes": list(row.get("reason_codes", [])),
            "label_status": row.get("status"),
            "historical_label": row.get("historical_label"),
            "price_identities": row.get("price_identities", {}),
            "feature_snapshot_hash": None if vector is None else vector.snapshot_hash,
            "feature_source_versions_hash": feature_sources.get(sample_id),
            "feature_available_date": None if vector is None else vector.available_date,
            "missing_feature_ids": [] if vector is None else list(vector.missing_feature_ids),
            "baseline_prediction": _prediction_pin(baseline_prediction),
            "candidate_prediction": _prediction_pin(candidate_prediction),
            "included_in_common_cohort": common,
            "research_limitations": research_limitations,
            "exclusion_reasons": sorted(set(reasons)),
        })
    common_ids.sort(key=lambda sample_id: (
        rows_by_id[sample_id]["decision_date"], rows_by_id[sample_id]["stock_code"], sample_id,
    ))
    report["member_ledger"] = ledger
    report["common_cohort"] = {
        "sample_ids": common_ids,
        "count": len(common_ids),
        "label_availability_unknown_research_only_count": sum(
            rows_by_id[sample_id].get("availability_status") == "unknown" for sample_id in common_ids),
        "contains_matched": any(rows_by_id[sample_id].get("member_state") == "matched" for sample_id in common_ids),
        "contains_notmatched_control": any(rows_by_id[sample_id].get("member_state") == "notmatched" for sample_id in common_ids),
        "both_roles_use_identical_ordered_sample_ids": True,
    }
    report["baseline"] = None if baseline_role is None else {
        "model_pin": _model_pin(baseline_role),
        "prediction_count": len(baseline_role["predictions"]),
        "common_cohort_count": len(common_ids),
        "metrics": None,
        "qualification": {"research_only": True, "training_eligible": False,
            "historical_pit_eligible": False, "formal_eligible": False,
            "natural_authority": False, "execution_eligible": False,
            "production_blend_alpha_bp": 0},
    }
    report["candidate"] = None if candidate_role is None else {
        "model_pin": _model_pin(candidate_role),
        "prediction_count": len(candidate_role["predictions"]),
        "common_cohort_count": len(common_ids),
        "metrics": None,
        "qualification": {"research_only": True, "training_eligible": False,
            "historical_pit_eligible": False, "formal_eligible": False,
            "natural_authority": False, "execution_eligible": False,
            "production_blend_alpha_bp": 0},
    }
    if normalized_comparison is None:
        report["status"] = report["readiness"] = "blocked_missing_configuration"
    elif bundle is None:
        report["reason_codes"] = sorted(set(report["reason_codes"]))
        report["status"] = report["readiness"] = "blocked_missing_inputs_bundle"
    elif bundle.get("baseline") is None:
        report["reason_codes"] = sorted(set(report["reason_codes"] + ["baseline_role_missing"]))
        report["status"] = report["readiness"] = "not_comparable_missing_baseline"
    elif bundle.get("candidate") is None:
        report["reason_codes"] = sorted(set(report["reason_codes"] + ["candidate_role_missing"]))
        report["status"] = report["readiness"] = "not_comparable_missing_candidate"
    elif baseline_role is None or candidate_role is None:
        report["status"] = report["readiness"] = "not_comparable_target_contract"
    elif not baseline_role["target_contract_matches"] or not candidate_role["target_contract_matches"]:
        report["reason_codes"] = sorted(set(report["reason_codes"] + ["target_contract_missing_or_incompatible"]))
        report["status"] = report["readiness"] = "not_comparable_target_contract"
    elif len(common_ids) == 0:
        report["reason_codes"] = ["no_common_evaluable_samples"]
        report["status"] = report["readiness"] = "not_evaluable"
    elif normalized_comparison["top_k"] > len(common_ids):
        report["reason_codes"] = ["top_k_exceeds_common_sample_count"]
        report["status"] = report["readiness"] = "not_evaluable"
    elif report["reason_codes"]:
        report["status"] = report["readiness"] = "not_comparable"
    else:
        if cancel():
            return _cancelled()
        baseline_metrics = _role_metrics(baseline_role, common_ids, rows_by_id, normalized_comparison)
        if cancel():
            return _cancelled()
        candidate_metrics = _role_metrics(candidate_role, common_ids, rows_by_id, normalized_comparison)
        if cancel():
            return _cancelled()
        assert baseline_metrics is not None and candidate_metrics is not None
        report["baseline"]["metrics"] = baseline_metrics
        report["candidate"]["metrics"] = candidate_metrics
        report["metric_differences"] = {
            name: candidate_metrics[name] - baseline_metrics[name]
            for name in baseline_metrics if name in candidate_metrics
        }
        report["status"] = report["readiness"] = "research_only_comparison"
    report["reason_codes"] = sorted(set(report["reason_codes"]))
    report["summary_text"] = _summary(report)
    if cancel():
        return _cancelled()
    return _seal_report(report)


def _summary(report: dict[str, Any]) -> str:
    status = report.get("status")
    denominators = report.get("cohort_denominators", {})
    full = denominators.get("selected_method_horizon_members", 0)
    parent = denominators.get("parent_member_rows", report.get("source_denominators", {}).get("represented_denominator_sum", 0))
    method_rows = denominators.get("method_member_rows", report.get("source_denominators", {}).get("method_member_rows", 0))
    common = report.get("common_cohort", {}).get("count", 0)
    lost = max(0, full - common)
    method = report.get("method_id") or "\u672a\u8a2d\u5b9a\u65b9\u6cd5"
    horizon = report.get("horizon")
    measure = report.get("measure") or "\u672a\u8a2d\u5b9a\u6a19\u7c64"
    population = f"\u7236\u5c64\u4ee3\u8868\u6bcd\u9ad4 {parent} \u540d\uff08\u65b9\u6cd5\u5217 {method_rows} \u7b46\uff09"
    if status == "research_only_comparison":
        baseline = report["baseline"]["metrics"]
        candidate = report["candidate"]["metrics"]
        delta = report["metric_differences"].get("mae_bp")
        return (f"ML \u516c\u5e73\u6bd4\u8f03\uff1a{method}\u3001H{horizon}\u3001{measure}\uff1b{population}\uff0c"
                f"\u6240\u9078\u65b9\u6cd5\uff0f\u671f\u9650 {full} \u7b46\uff0c\u5171\u540c\u53ef\u8a55 {common} \u7b46\uff0c\u672a\u9032\u5171\u540c\u8a55\u5206 {lost} \u7b46\u3002"
                f"Baseline MAE {baseline['mae_bp']} bp\uff0cCandidate MAE {candidate['mae_bp']} bp\uff0cCandidate-Baseline MAE {delta:+d} bp\u3002Top-K \u662f\u8a55\u4f30\u7a97\u5167 pooled \u7814\u7a76\u6392\u5e8f\uff1b"
                "coverage \u50c5\u8868\u793a\u5171\u540c\u6a23\u672c\u6db5\u84cb\u7387\u3002\u7d50\u679c\u9650\u7814\u7a76\u7528\u9014\uff0c\u4e0d\u4ee3\u8868 PIT \u6216\u4ea4\u6613\u8cc7\u683c\u3002")
    if status == "not_comparable_missing_baseline":
        return (f"ML \u516c\u5e73\u6bd4\u8f03\u672a\u5b8c\u6210\uff1a\u7f3a\u5c11 baseline \u57fa\u6e96\u6a21\u578b\u8f38\u5165\uff1b{population}\uff0c"
                f"\u6240\u9078\u65b9\u6cd5\uff0f\u671f\u9650 {full} \u7b46\uff0c\u5171\u540c\u53ef\u8a55 {common} \u7b46\uff1b\u672a\u8a08\u7b97\u5169\u6a21\u578b\u6307\u6a19\u3002")
    if status == "not_comparable_missing_candidate":
        return (f"ML \u516c\u5e73\u6bd4\u8f03\u672a\u5b8c\u6210\uff1a\u7f3a\u5c11\u5019\u9078\u6a21\u578b\uff08candidate\uff09\u8f38\u51fa\uff1b{population}\uff0c"
                f"\u6240\u9078\u65b9\u6cd5\uff0f\u671f\u9650 {full} \u7b46\uff0c\u5171\u540c\u53ef\u8a55 {common} \u7b46\uff1b\u672a\u8a08\u7b97\u5169\u6a21\u578b\u6307\u6a19\u3002")
    if status == "not_evaluable":
        reason = "\u5171\u540c\u53ef\u8a55\u6a23\u672c\u70ba 0" if common == 0 else "\u6307\u5b9a top-k \u8d85\u904e\u5171\u540c\u6a23\u672c\u6578"
        return f"ML \u516c\u5e73\u6bd4\u8f03\u4e0d\u53ef\u8a55\u4f30\uff1a{method}\u3001H{horizon} {measure}\uff1b{population}\u3001\u6240\u9078 {full} \u7b46\u3001\u5171\u540c {common} \u7b46\uff1b{reason}\uff0c\u6307\u6a19\u70ba\u7a7a\u3002"
    if status == "blocked_missing_inputs_bundle":
        return f"ML \u516c\u5e73\u6bd4\u8f03\u5c1a\u672a\u57f7\u884c\uff1a\u7f3a\u5c11 CORE20 \u7279\u5fb5\u8207 Baseline/Candidate bundle\uff1b{population}\u3001\u6240\u9078 {full} \u7b46\uff0c\u672a\u8a08\u5206\u3002"
    if status == "blocked_missing_configuration":
        return f"ML \u516c\u5e73\u6bd4\u8f03\u7f3a\u5c11\u660e\u793a\u8a2d\u5b9a\uff1b{population}\u5df2\u4fdd\u7559\uff0c\u4e0d\u8a08\u5206\u3002"
    return f"ML \u516c\u5e73\u6bd4\u8f03\u7121\u6cd5\u5b8c\u6210\uff1a{method}\u3001H{horizon} {measure}\uff1b{population}\u3001\u6240\u9078 {full} \u7b46\u3001\u5171\u540c {common} \u7b46\uff1b\u8acb\u6aa2\u67e5\u7f3a\u4ef6\u8207\u76f8\u5bb9\u6027\u8a3a\u65b7\u3002"
