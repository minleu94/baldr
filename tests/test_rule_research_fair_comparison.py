"""Synthetic exported DTOs over exact sealed UX21 labels; no model is fit."""

from __future__ import annotations

from dataclasses import asdict
import copy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from app_module import rule_research_fair_comparison as fair_module
from app_module.rule_research_fair_comparison import (
    BUNDLE_SCHEMA,
    COMPARISON_SCHEMA,
    MAX_BYTES,
    _feature_contract,
    build_fair_comparison,
    comparison_binding,
    comparison_target_contract,
)
from app_module.rule_research_forward_store import run_forward_isolated
from app_module.rule_research_label_readiness import build_label_readiness_batch
from app_module.rule_research_parent_capture import produce_parent_rule_samples
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.historical_contracts import HistoricalFeatureRow
from ml_module.historical_feature_builder import HistoricalFeatureBuilder
from ml_module.inference_contracts import ShadowInferenceRequest, prediction_id_for
from ml_module.model_prediction_registries import MLModelRecord, MLShadowPredictionRecord
from tests.test_rule_research_benchmark_integration import _prepare
from tests.test_rule_research_forward_isolated import pipeline


def _prepared(pipeline):
    """Return one true sealed source pair plus strict label/split/metric policies."""
    args, _old_parent, config, runtime, _policy_path, _acceptance = pipeline
    # Create one real notmatched comparison member, then capture a new parent.
    # The existing sealed parent and database fixture are retained untouched
    # outside this temporary test tree.
    with sqlite3.connect(args["db_path"]) as connection:
        connection.execute(
            "UPDATE technical_indicators SET MA20=? WHERE 證券代號=?",
            ("200", "1001"),
        )
        assert connection.total_changes == 1
    produced = produce_parent_rule_samples(**args)
    assert produced["status"] == "complete", produced
    parent = (args["capture_root"] / "parents"
              / produced["parent_capture"]["receipt"]["capture_identity_sha256"] / "receipt.json")
    config["parent_receipt"] = str(parent)
    runtime.write_text(json.dumps(config), encoding="utf-8")
    _args, parent, _config, runtime, _benchmark_db = _prepare(
        (args, parent, config, runtime, _policy_path, _acceptance),
    )
    preview = run_forward_isolated(runtime)
    assert preview["status"] == "preflight_passed", preview
    decision = date.fromisoformat(preview["projection"]["decision_date"])
    split_policy = {
        "schema_version": "rule-research-label-split.v1",
        "split_id": "synthetic-research-window-v1",
        "version": "1",
        "train_start": (decision - timedelta(days=45)).isoformat(),
        "train_end": (decision - timedelta(days=10)).isoformat(),
        "evaluation_start": decision.isoformat(),
        "evaluation_end": decision.isoformat(),
        "training_as_of": (decision - timedelta(days=2)).isoformat(),
    }
    label_policy = {
        "schema_version": "rule-research-label-policy.v1",
        "policy_id": "synthetic-gross-five-day-v1",
        "version": "1",
        "measure": "gross",
        "horizons": [5],
    }
    saved = run_forward_isolated(runtime, execute=True)
    assert saved["status"] == "saved", saved
    receipts = [(parent, Path(saved["receipt_path"]))]
    label_report = build_label_readiness_batch(receipts, label_policy, split_policy)
    assert label_report["status"] == "research_only", label_report
    candidates = [row for row in label_report["label_rows"]
                  if row["horizon"] == "H5" and row["split_role"] == "evaluation_window_research_only"
                  and row["member_state"] in {"matched", "notmatched"} and type(row["value_bp"]) is int]
    method_counts = {}
    method_states = {}
    for row in candidates:
        method_counts[row["method_id"]] = method_counts.get(row["method_id"], 0) + 1
        method_states.setdefault(row["method_id"], set()).add(row["member_state"])
    method_id = next(
        method for method, states in method_states.items()
        if {"matched", "notmatched"} <= states
    )
    comparison_policy = {
        "schema_version": COMPARISON_SCHEMA,
        "policy_id": "synthetic-return-comparison-v1",
        "version": "1",
        "method_id": method_id,
        "horizon": 5,
        "metrics": "return_only",
        "top_k": 1,
        "downside_threshold_bp": None,
    }
    assert method_counts[method_id] >= 2, method_counts
    assert {"matched", "notmatched"} <= method_states[method_id]
    return receipts, label_policy, split_policy, comparison_policy


def _bundle_for(report, policy, *, missing_feature_ids=(), omit_feature_samples=(),
                omit_candidate_sample=None, zero_prediction_sample=None):
    """Build JSON-shaped synthetic 20-slot features and immutable prediction DTOs."""
    selected = [row for row in report["label_rows"]
                if row["method_id"] == policy["method_id"] and row["horizon"] == f"H{policy['horizon']}"]
    registry_hash, schema_hash = _feature_contract()
    builder = HistoricalFeatureBuilder()
    target_contract = comparison_target_contract(report, policy)
    dataset_id = "synthetic-pinned-dataset-v1"
    feature_source_hash = "sha256:" + hashlib.sha256(b"synthetic-feature-source-v1").hexdigest()
    features = []
    vectors = {}
    for index, row in enumerate(selected):
        if row["sample_id"] in omit_feature_samples:
            continue
        decision = date.fromisoformat(row["decision_date"])
        prior = (decision - timedelta(days=1)).isoformat()
        values = [(feature_id, index * 100 + slot)
                  for slot, feature_id in enumerate(CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids)]
        if row["sample_id"] in missing_feature_ids:
            values[0] = (values[0][0], None)
        feature = HistoricalFeatureRow(
            symbol=row["stock_code"], decision_date=row["decision_date"],
            feature_as_of_date=prior, available_date=prior, values=tuple(values),
        )
        vector = builder.load(feature)
        vectors[row["sample_id"]] = vector
        features.append({
            "sample_id": row["sample_id"],
            "source_versions_hash": feature_source_hash,
            "feature": {
                "symbol": feature.symbol,
                "decision_date": feature.decision_date,
                "feature_as_of_date": feature.feature_as_of_date,
                "available_date": feature.available_date,
                "values": [[name, value] for name, value in feature.values],
            },
        })
    split = report["split_policy"]["value"]
    audit = {
        "training_as_of": split["training_as_of"],
        "max_train_decision_date": split["train_end"],
        "max_train_label_available_date": split["training_as_of"],
    }
    roles = []
    for name, predicted_return, base_rank in (("baseline", 100, 2000), ("candidate", 125, 6500)):
        model = MLModelRecord(
            model_id=f"synthetic-{name}-v1", dataset_id=dataset_id,
            created_at="2026-10-06T00:00:00+00:00", model_family="controlled-test-model",
            feature_names=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids,
            artifact_path=f"synthetic://{name}",
            artifact_hash="sha256:" + hashlib.sha256(name.encode("utf-8")).hexdigest(),
        )
        predictions = []
        for index, row in enumerate(selected):
            if row["sample_id"] not in vectors:
                continue
            if name == "candidate" and row["sample_id"] == omit_candidate_sample:
                continue
            vector = vectors[row["sample_id"]]
            prediction_return = 0 if row["sample_id"] == zero_prediction_sample else predicted_return + index
            ranking = base_rank + index
            request = ShadowInferenceRequest(
                model_id=model.model_id, dataset_id=dataset_id,
                decision_date=row["decision_date"],
                feature_snapshot_hash=vector.snapshot_hash,
                feature_registry_hash=registry_hash,
                source_versions={"decision_feature_source": feature_source_hash},
                feature_max_available_date=vector.available_date,
            )
            record = MLShadowPredictionRecord(
                prediction_id=prediction_id_for(request, row["stock_code"]),
                model_id=model.model_id, dataset_id=dataset_id,
                symbol=row["stock_code"], decision_date=row["decision_date"],
                available_date=vector.available_date,
                return_prediction_bp=prediction_return, ranking_score=ranking,
                downside_probability=1800 + index, uncertainty_bp=300,
                feature_snapshot_hash=vector.snapshot_hash,
                source_versions_hash=feature_source_hash,
            )
            predictions.append({"sample_id": row["sample_id"], "record": asdict(record)})
        roles.append({
            "model_record": {**asdict(model), "feature_names": list(model.feature_names)},
            "training_audit": audit,
            "target_contract": dict(target_contract),
            "predictions": predictions,
        })
    return {
        "schema_version": BUNDLE_SCHEMA,
        "version": "1",
        "binding_sha256": comparison_binding(report, policy),
        "dataset_id": dataset_id,
        "feature_registry_hash": registry_hash,
        "feature_schema_hash": schema_hash,
        "features": features,
        "baseline": roles[0],
        "candidate": roles[1],
    }


def test_sealed_labels_compare_same_common_matched_cohort(pipeline):
    receipts, labels, split, policy = _prepared(pipeline)
    source_report = build_label_readiness_batch(receipts, labels, split)
    bundle = _bundle_for(source_report, policy)
    result = build_fair_comparison(receipts, labels, split, policy, bundle)

    assert result["status"] == "research_only_comparison"
    assert result["metric_scope"] == "pooled_common_samples_in_selected_evaluation_window"
    assert result["common_cohort"]["both_roles_use_identical_ordered_sample_ids"] is True
    assert result["common_cohort"]["contains_matched"] is True
    assert result["common_cohort"]["contains_notmatched_control"] is True
    assert result["common_cohort"]["count"] >= 2
    assert result["cohort_denominators"]["matched_controls_in_denominator"] == result["cohort_denominators"]["member_state_counts"]["notmatched"]
    assert result["cohort_denominators"]["selected_method_horizon_members"] >= result["common_cohort"]["count"]
    assert result["cohort_denominators"]["parent_member_rows"] == result["source_denominators"]["represented_denominator_sum"]
    assert result["cohort_denominators"]["method_member_rows"] == result["source_denominators"]["method_member_rows"]
    assert result["cohort_denominators"]["parent_member_rows"] == 3
    assert result["cohort_denominators"]["method_member_rows"] == 6
    assert result["cohort_denominators"]["selected_method_horizon_members"] == 3
    assert result["common_cohort"]["count"] == 2
    assert result["baseline"]["metrics"]["coverage_bp"] == 10000
    assert result["candidate"]["metrics"]["coverage_bp"] == 10000
    assert "coverage_bp" not in result["cohort_denominators"]
    assert result["baseline"]["qualification"]["training_eligible"] is False
    assert result["candidate"]["qualification"]["historical_pit_eligible"] is False
    assert result["production_blend_alpha_bp"] == 0
    assert result["selection_status"] == "unknown"
    assert result["source_semantics"]["current_observed_availability_never_becomes_pit"] is True
    assert result["common_cohort"]["label_availability_unknown_research_only_count"] >= 1
    assert "ML 公平比較" in result["summary_text"]
    assert result["report_identity_sha256"].startswith("sha256:")


def test_missing_policy_still_reads_and_reports_sealed_parent_denominator(pipeline):
    receipts, _labels, _split, _policy = _prepared(pipeline)
    result = build_fair_comparison(receipts, None, None)
    assert result["status"] == "blocked_missing_configuration"
    assert result["source_denominators"]["method_member_rows"] >= 3
    assert result["common_cohort"]["count"] == 0
    assert result["baseline"] is None and result["candidate"] is None
    assert result["training_eligible"] is False


def test_missing_candidate_is_not_empty_success(pipeline):
    receipts, labels, split, policy = _prepared(pipeline)
    report = build_label_readiness_batch(receipts, labels, split)
    bundle = _bundle_for(report, policy)
    bundle["candidate"] = None
    result = build_fair_comparison(receipts, labels, split, policy, bundle)
    assert result["status"] == "not_comparable_missing_candidate"
    assert result["candidate"] is None
    assert result["baseline"]["metrics"] is None
    assert "candidate_role_missing" in result["reason_codes"]
    assert all("candidate_role_missing" in row["exclusion_reasons"] for row in result["member_ledger"])
    assert "候選模型" in result["summary_text"]


def test_missing_baseline_is_not_empty_success(pipeline):
    receipts, labels, split, policy = _prepared(pipeline)
    report = build_label_readiness_batch(receipts, labels, split)
    bundle = _bundle_for(report, policy)
    bundle["baseline"] = None
    result = build_fair_comparison(receipts, labels, split, policy, bundle)
    assert result["status"] == "not_comparable_missing_baseline"
    assert result["baseline"] is None
    assert result["candidate"]["metrics"] is None
    assert "baseline_role_missing" in result["reason_codes"]
    assert all("baseline_role_missing" in row["exclusion_reasons"] for row in result["member_ledger"])


def test_absent_one_sided_prediction_stays_in_denominator_and_is_not_intersected_silently(pipeline):
    receipts, labels, split, policy = _prepared(pipeline)
    report = build_label_readiness_batch(receipts, labels, split)
    target = next(row["sample_id"] for row in report["label_rows"]
                  if row["method_id"] == policy["method_id"] and row["horizon"] == "H5"
                  and row["member_state"] in {"matched", "notmatched"})
    bundle = _bundle_for(report, policy, omit_candidate_sample=target)
    result = build_fair_comparison(receipts, labels, split, policy, bundle)
    assert result["cohort_denominators"]["selected_method_horizon_members"] >= result["common_cohort"]["count"] + 1
    assert any(row["sample_id"] == target and "candidate_prediction_missing" in row["exclusion_reasons"]
               for row in result["member_ledger"])
    assert result["status"] == "research_only_comparison"


def test_explicit_downside_policy_and_integer_zero_prediction_are_scored(pipeline):
    receipts, labels, split, policy = _prepared(pipeline)
    policy = {**policy, "metrics": "return_and_downside", "downside_threshold_bp": 0}
    report = build_label_readiness_batch(receipts, labels, split)
    zero_sample = next(row["sample_id"] for row in report["label_rows"]
                       if row["method_id"] == policy["method_id"] and row["horizon"] == "H5"
                       and row["member_state"] in {"matched", "notmatched"})
    bundle = _bundle_for(report, policy, zero_prediction_sample=zero_sample)
    result = build_fair_comparison(receipts, labels, split, policy, bundle)
    assert result["status"] == "research_only_comparison"
    assert "brier_bp" in result["baseline"]["metrics"]
    assert result["expected_target_contract"]["downside_threshold_bp"] == 0
    assert result["candidate"]["metrics"]["coverage_bp"] == 10000
    scored_zero = next(row for row in result["member_ledger"] if row["sample_id"] == zero_sample)
    assert scored_zero["baseline_prediction"]["return_prediction_bp"] == 0


@pytest.mark.parametrize("mutation,reason", [
    ("source_hash", "prediction_feature_source_binding_mismatch"),
    ("artifact_hash", "model_artifact_sha256_invalid"),
    ("dataset", "model_dataset_mismatch"),
    ("audit", "training_audit_temporal_mismatch"),
    ("float_prediction", "prediction_values_must_be_integer_bp"),
    ("model_id_type", "model_model_id_invalid"),
    ("prediction_symbol_type", "prediction_symbol_invalid"),
])
def test_invalid_source_dataset_artifact_audit_and_numeric_pins_fail_closed(pipeline, mutation, reason):
    receipts, labels, split, policy = _prepared(pipeline)
    report = build_label_readiness_batch(receipts, labels, split)
    bundle = _bundle_for(report, policy)
    record = bundle["baseline"]["predictions"][0]["record"]
    if mutation == "source_hash":
        record["source_versions_hash"] = "sha256:" + "f" * 64
    elif mutation == "artifact_hash":
        bundle["baseline"]["model_record"]["artifact_hash"] = "not-a-hash"
    elif mutation == "dataset":
        bundle["candidate"]["model_record"]["dataset_id"] = "different-dataset"
    elif mutation == "audit":
        bundle["baseline"]["training_audit"]["training_as_of"] = split["evaluation_start"]
    elif mutation == "float_prediction":
        record["return_prediction_bp"] = 1.5
    elif mutation == "model_id_type":
        bundle["baseline"]["model_record"]["model_id"] = 17
    elif mutation == "prediction_symbol_type":
        record["symbol"] = 1001
    with pytest.raises(ValueError, match=reason):
        build_fair_comparison(receipts, labels, split, policy, bundle)


def test_feature_none_is_reported_as_missing_and_never_filled_with_zero(pipeline):
    receipts, labels, split, policy = _prepared(pipeline)
    report = build_label_readiness_batch(receipts, labels, split)
    missing_id = next(row["sample_id"] for row in report["label_rows"]
                      if row["method_id"] == policy["method_id"] and row["horizon"] == "H5"
                      and row["member_state"] in {"matched", "notmatched"})
    bundle = _bundle_for(report, policy, missing_feature_ids=(missing_id,))
    result = build_fair_comparison(receipts, labels, split, policy, bundle)
    row = next(row for row in result["member_ledger"] if row["sample_id"] == missing_id)
    assert row["included_in_common_cohort"] is False
    assert row["missing_feature_ids"]
    assert any(reason.startswith("feature_value_missing:") for reason in row["exclusion_reasons"])


def test_bundle_binding_is_posthoc_and_policy_or_target_semantics_cannot_mix(pipeline):
    receipts, labels, split, policy = _prepared(pipeline)
    report = build_label_readiness_batch(receipts, labels, split)
    bundle = _bundle_for(report, policy)
    wrong_policy = {**policy, "top_k": 2}
    with pytest.raises(ValueError, match="fair_bundle_binding_mismatch"):
        build_fair_comparison(receipts, labels, split, wrong_policy, bundle)
    bundle = _bundle_for(report, policy)
    bundle["candidate"]["target_contract"]["measure"] = "net"
    result = build_fair_comparison(receipts, labels, split, policy, bundle)
    assert result["status"] == "not_comparable_target_contract"
    assert result["candidate"]["metrics"] is None
    assert "target_contract_missing_or_incompatible" in result["reason_codes"]


def test_missing_model_target_contract_is_plain_not_comparable_with_row_reasons(pipeline):
    receipts, labels, split, policy = _prepared(pipeline)
    report = build_label_readiness_batch(receipts, labels, split)
    bundle = _bundle_for(report, policy)
    bundle["candidate"].pop("target_contract")
    result = build_fair_comparison(receipts, labels, split, policy, bundle)
    assert result["status"] == "not_comparable_target_contract"
    assert result["candidate"]["metrics"] is None
    assert "target_contract_missing_or_incompatible" in result["reason_codes"]
    assert all("candidate_target_contract_incompatible" in row["exclusion_reasons"]
               for row in result["member_ledger"])


def test_top_k_above_common_count_is_not_shrunk_and_metrics_stay_none(pipeline):
    receipts, labels, split, policy = _prepared(pipeline)
    report = build_label_readiness_batch(receipts, labels, split)
    policy = {**policy, "top_k": 10_000}
    bundle = _bundle_for(report, policy)
    result = build_fair_comparison(receipts, labels, split, policy, bundle)
    assert result["status"] == "not_evaluable"
    assert result["baseline"]["metrics"] is None
    assert result["candidate"]["metrics"] is None
    assert result["reason_codes"] == ["top_k_exceeds_common_sample_count"]


def test_bundle_byte_bound_rejects_instead_of_truncating(pipeline):
    receipts, labels, split, policy = _prepared(pipeline)
    report = build_label_readiness_batch(receipts, labels, split)
    bundle = _bundle_for(report, policy)
    bundle["oversized_test_payload"] = "x" * MAX_BYTES
    with pytest.raises(ValueError, match="fair_inputs_bundle_byte_bound"):
        build_fair_comparison(receipts, labels, split, policy, bundle)


def test_cancel_has_no_partial_result_and_retry_is_identity_stable(pipeline):
    receipts, labels, split, policy = _prepared(pipeline)
    report = build_label_readiness_batch(receipts, labels, split)
    bundle = _bundle_for(report, policy)
    cancelled = build_fair_comparison(receipts, labels, split, policy, bundle, cancel_callback=lambda: True)
    assert cancelled["status"] == "cancelled"
    assert cancelled["member_ledger"] == []
    first = build_fair_comparison(receipts, labels, split, policy, bundle)
    again = build_fair_comparison(receipts, labels, split, policy, bundle)
    assert first["report_identity_sha256"] == again["report_identity_sha256"]
    assert first["bundle_identity_sha256"] == again["bundle_identity_sha256"]
    reordered = copy.deepcopy(bundle)
    reordered["features"].reverse()
    reordered["baseline"]["predictions"].reverse()
    reordered["candidate"]["predictions"].reverse()
    same = build_fair_comparison(receipts, labels, split, policy, reordered)
    assert first["report_identity_sha256"] == same["report_identity_sha256"]
    assert first["bundle_identity_sha256"] == same["bundle_identity_sha256"]


def test_cancel_during_first_scorer_discards_all_metrics_and_can_retry(pipeline, monkeypatch):
    receipts, labels, split, policy = _prepared(pipeline)
    report = build_label_readiness_batch(receipts, labels, split)
    bundle = _bundle_for(report, policy)
    should_cancel = [False]
    scorer = fair_module.evaluate_return_predictions

    def cancel_after_baseline_score(**kwargs):
        result = scorer(**kwargs)
        should_cancel[0] = True
        return result

    monkeypatch.setattr(fair_module, "evaluate_return_predictions", cancel_after_baseline_score)
    cancelled = build_fair_comparison(
        receipts, labels, split, policy, bundle, cancel_callback=lambda: should_cancel[0],
    )
    assert cancelled["status"] == "cancelled"
    assert cancelled["member_ledger"] == []
    assert cancelled["baseline"] is None and cancelled["candidate"] is None
    should_cancel[0] = False
    monkeypatch.setattr(fair_module, "evaluate_return_predictions", scorer)
    retry = build_fair_comparison(receipts, labels, split, policy, bundle)
    assert retry["status"] == "research_only_comparison"
