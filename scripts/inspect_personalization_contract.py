"""執行 bounded V6 personalization contract fixture 的離線檢查。

這個 runner 只建立記憶體 fixture，呼叫 read-only projection 與固定 fit/evaluate
contract，不讀正式資料根目錄、不啟動 scheduler、不建立 active pointer，也不
宣稱 adoption 或 performance improvement。``--output`` 僅允許 create-only 寫入
檢查 receipt；既有檔案內容不會被覆寫。
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from app_module.personalization_calibration import (
    PersonalizationCalibrationEvaluator,
    PersonalizationCalibrationPolicy,
)
from app_module.personalization_contract import (
    PersonalizationDeliveryScope,
    PersonalizationEvaluationRow,
    canonical_payload_hash,
)
from app_module.personalization_projection import (
    PersonalizationDeliveryCaptureService,
    PersonalizationProjectionService,
)


RUNNER_RECEIPT_SCHEMA_VERSION = "personalization-contract-runner-receipt.v1"
FIXTURE_RESULT_ID = "rec_personalization_fixture_001"
FIXTURE_STOCK_CODE = "2330"
FIXTURE_SCOPE_ID = "scope_fixture_user_001"
FIXTURE_DELIVERY_ID = "delivery_fixture_001"
FIXTURE_REQUEST_ID = "request_fixture_001"
FIXTURE_PREDICTION_ID = "00000000-0000-0000-0000-000000000001"
FIXTURE_RECEIPT_HASH_SEED = "fixture-projection-receipt"
FIXTURE_COST_HASH = "sha256:" + ("1" * 64)
FIXTURE_DATASET_HASH = "sha256:" + ("2" * 64)
FIXTURE_UNIVERSE_HASH = "sha256:" + ("3" * 64)
FIXTURE_LABEL_CONTRACT_ID = "personalization-label-fixture.v1"
FIXTURE_RETURN_BASIS = "close_to_close_event_date"


def _fixture_receipt() -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "recommendation-calibration-projection-receipt.v1",
        "receipt_kind": "recommendation_inference_projection",
        "decision_date": "2025-02-10",
        "result_id": FIXTURE_RESULT_ID,
        "candidate_identity": {
            "candidate_id": "model_fixture_v1",
            "model_id": "model_fixture_v1",
        },
        "training_provenance": {
            "status": "legacy_unproven",
            "dataset_id": "dataset_fixture_v1",
            "dataset_hash": FIXTURE_DATASET_HASH,
        },
        "inference_provenance": {
            "status": "verified",
            "decision_date": "2025-02-10",
            "probability_transform_id": "recommendation-probability-transform.v1",
            "source_id": "recommendation_service",
        },
        "provenance_compatibility": {"status": "legacy_unproven"},
        "selection_contract": {
            "authority": "rule_top_n",
            "score_kind": "rule_total_score",
            "percentile_kind": "rule_percentile",
            "model_ranking_kind": "model_return_bp",
            "top_n_changed_by_model": False,
        },
        "cost_scenario_hash": FIXTURE_COST_HASH,
        "model_id": "model_fixture_v1",
        "dataset_id": "dataset_fixture_v1",
        "dataset_hash": FIXTURE_DATASET_HASH,
        "label_contract_id": FIXTURE_LABEL_CONTRACT_ID,
        "return_basis": FIXTURE_RETURN_BASIS,
        "universe_policy_hash": FIXTURE_UNIVERSE_HASH,
        "source_id": "recommendation_service",
        "projections": [
            {
                "stock_code": FIXTURE_STOCK_CODE,
                "ranking_score_bp": 8200,
                "ranking_percentile_bp": 9000,
                "calibrated_probability_bp": 5000,
                "model_version": "model_fixture_v1",
                "dataset_version": "dataset_fixture_v1",
                "dataset_hash": FIXTURE_DATASET_HASH,
                "cost_scenario_hash": FIXTURE_COST_HASH,
                "horizon": "20 trading days",
                "prediction_id": FIXTURE_PREDICTION_ID,
                "label_contract_id": FIXTURE_LABEL_CONTRACT_ID,
                "return_basis": FIXTURE_RETURN_BASIS,
                "universe_policy_hash": FIXTURE_UNIVERSE_HASH,
                "status": "active_candidate",
            }
        ],
        "shadow_only": True,
        "formal_order_allowed": False,
        "production_action_allowed": False,
    }
    body["result_identity_hash"] = canonical_payload_hash(
        {
            "result_id": FIXTURE_RESULT_ID,
            "decision_date": "2025-02-10",
            "candidate_id": "model_fixture_v1",
            "stock_codes": [FIXTURE_STOCK_CODE],
            "projection_rows_sha256": canonical_payload_hash(body["projections"]),
        }
    )
    body["projection_rows_sha256"] = canonical_payload_hash(body["projections"])
    body["receipt_hash_seed"] = FIXTURE_RECEIPT_HASH_SEED
    receipt_hash = canonical_payload_hash(body)
    return {**body, "receipt_hash": receipt_hash}


def _fixture_scope() -> PersonalizationDeliveryScope:
    return PersonalizationDeliveryScope.create(
        scope_id=FIXTURE_SCOPE_ID,
        scope_type="user",
        delivery_id=FIXTURE_DELIVERY_ID,
        declared_at="2025-02-10T08:50:00+00:00",
        decision_at="2025-02-10T09:00:00+00:00",
        available_at="2025-02-10T08:55:00+00:00",
        captured_at="2025-02-10T08:55:00+00:00",
        receipt_created_at="2025-02-10T09:01:00+00:00",
    )


def _fixture_rows() -> tuple[PersonalizationEvaluationRow, ...]:
    common: dict[str, Any] = {
        "scope_id": FIXTURE_SCOPE_ID,
        "symbol": FIXTURE_STOCK_CODE,
        "horizon_days": 20,
        "cost_scenario_hash": FIXTURE_COST_HASH,
        "decision_at": "2025-01-01T09:00:00+00:00",
        "available_at": "2025-01-01T08:55:00+00:00",
        "captured_at": "2025-01-01T08:55:00+00:00",
        "receipt_created_at": "2025-01-01T09:01:00+00:00",
        "label_available_at": "2025-01-21T00:00:00+00:00",
        "outcome_recorded_at": "2025-01-21T00:00:00+00:00",
        "delivery_status": "delivered",
        "outcome_status": "ready",
        "outcome_tier": "natural_forward",
        "source_id": "recommendation_service",
        "prediction_receipt_hash": "sha256:" + ("4" * 64),
        "model_id": "model_fixture_v1",
        "dataset_id": "dataset_fixture_v1",
        "dataset_hash": FIXTURE_DATASET_HASH,
        "universe_policy_hash": FIXTURE_UNIVERSE_HASH,
        "label_contract_id": FIXTURE_LABEL_CONTRACT_ID,
        "return_basis": FIXTURE_RETURN_BASIS,
    }
    return (
        PersonalizationEvaluationRow(
            prediction_id="00000000-0000-0000-0000-000000000010",
            decision_date="2025-01-01",
            label_available_date="2025-01-21",
            population_probability_bp=5000,
            label=1,
            row_id="fit_001",
            **common,
        ),
        PersonalizationEvaluationRow(
            prediction_id="00000000-0000-0000-0000-000000000011",
            decision_date="2025-01-02",
            label_available_date="2025-01-22",
            population_probability_bp=5000,
            label=0,
            row_id="fit_002",
            decision_at="2025-01-02T09:00:00+00:00",
            available_at="2025-01-02T08:55:00+00:00",
            captured_at="2025-01-02T08:55:00+00:00",
            receipt_created_at="2025-01-02T09:01:00+00:00",
            label_available_at="2025-01-22T00:00:00+00:00",
            outcome_recorded_at="2025-01-22T00:00:00+00:00",
            **{key: value for key, value in common.items() if key not in {
                "decision_at", "available_at", "captured_at", "receipt_created_at",
                "label_available_at", "outcome_recorded_at"
            }},
        ),
    )


def _fixture_evaluation_rows() -> tuple[PersonalizationEvaluationRow, ...]:
    return (
        PersonalizationEvaluationRow(
            prediction_id="00000000-0000-0000-0000-000000000020",
            scope_id=FIXTURE_SCOPE_ID,
            symbol=FIXTURE_STOCK_CODE,
            decision_date="2025-02-25",
            label_available_date="2025-03-17",
            horizon_days=20,
            cost_scenario_hash=FIXTURE_COST_HASH,
            population_probability_bp=5000,
            label=1,
            row_id="eval_001",
            decision_at="2025-02-25T09:00:00+00:00",
            available_at="2025-02-25T08:55:00+00:00",
            captured_at="2025-02-25T08:55:00+00:00",
            receipt_created_at="2025-02-25T09:01:00+00:00",
            label_available_at="2025-03-17T00:00:00+00:00",
            outcome_recorded_at="2025-03-17T00:00:00+00:00",
            delivery_status="delivered",
            outcome_status="ready",
            outcome_tier="natural_forward",
            source_id="recommendation_service",
            prediction_receipt_hash="sha256:" + ("4" * 64),
            model_id="model_fixture_v1",
            dataset_id="dataset_fixture_v1",
            dataset_hash=FIXTURE_DATASET_HASH,
            universe_policy_hash=FIXTURE_UNIVERSE_HASH,
            label_contract_id=FIXTURE_LABEL_CONTRACT_ID,
            return_basis=FIXTURE_RETURN_BASIS,
        ),
        PersonalizationEvaluationRow(
            prediction_id="00000000-0000-0000-0000-000000000021",
            scope_id=FIXTURE_SCOPE_ID,
            symbol="2317",
            decision_date="2025-02-26",
            label_available_date="2025-03-18",
            horizon_days=20,
            cost_scenario_hash=FIXTURE_COST_HASH,
            population_probability_bp=5000,
            label=0,
            row_id="eval_002",
            decision_at="2025-02-26T09:00:00+00:00",
            available_at="2025-02-26T08:55:00+00:00",
            captured_at="2025-02-26T08:55:00+00:00",
            receipt_created_at="2025-02-26T09:01:00+00:00",
            label_available_at="2025-03-18T00:00:00+00:00",
            outcome_recorded_at="2025-03-18T00:00:00+00:00",
            delivery_status="delivered",
            outcome_status="ready",
            outcome_tier="natural_forward",
            source_id="recommendation_service",
            prediction_receipt_hash="sha256:" + ("4" * 64),
            model_id="model_fixture_v1",
            dataset_id="dataset_fixture_v1",
            dataset_hash=FIXTURE_DATASET_HASH,
            universe_policy_hash=FIXTURE_UNIVERSE_HASH,
            label_contract_id=FIXTURE_LABEL_CONTRACT_ID,
            return_basis=FIXTURE_RETURN_BASIS,
        ),
    )


def run_fixture() -> dict[str, Any]:
    """Return a deterministic, bounded runner receipt."""

    receipt = _fixture_receipt()
    scope = _fixture_scope()
    capture_service = PersonalizationDeliveryCaptureService()
    generated = capture_service.capture(
        scope=scope,
        request_id=FIXTURE_REQUEST_ID,
        result_id=FIXTURE_RESULT_ID,
        stock_code=FIXTURE_STOCK_CODE,
        projection_receipt_hash=str(receipt["receipt_hash"]),
        generated_at="2025-02-10T08:50:00+00:00",
        prediction_id=FIXTURE_PREDICTION_ID,
        model_id="model_fixture_v1",
        dataset_id="dataset_fixture_v1",
        dataset_hash="sha256:" + ("2" * 64),
        cost_scenario_hash=FIXTURE_COST_HASH,
        horizon_days=20,
    )
    persisted = capture_service.mark_persisted(
        generated,
        persisted_at="2025-02-10T08:55:00+00:00",
    )
    delivered = capture_service.mark_delivered(
        persisted,
        delivered_at="2025-02-10T08:59:00+00:00",
    )
    result: dict[str, Any] = {
        "result_id": FIXTURE_RESULT_ID,
        "run_context": {
            "as_of_date": "2025-02-10",
            "personalization_delivery_captures": [delivered.to_dict()],
            "calibration_projection_rows": {
                FIXTURE_STOCK_CODE: dict(receipt["projections"][0]),
            },
        },
        "recommendations": [
            {
                "stock_code": FIXTURE_STOCK_CODE,
                "calibrated_probability_bp": 5000,
                "calibration_provenance": {
                    "projection_receipt_hash": receipt["receipt_hash"],
                    "model_version": "model_fixture_v1",
                    "dataset_version": "dataset_fixture_v1",
                    "cost_scenario_hash": FIXTURE_COST_HASH,
                },
            }
        ],
    }
    capture_service.verify_saved_capture(result, delivered)

    action_reader: dict[tuple[str, str], list[Any]] = {
        (FIXTURE_RESULT_ID, FIXTURE_STOCK_CODE): [],
    }
    outcome_reader: dict[tuple[str, str], list[Any]] = {
        (FIXTURE_RESULT_ID, FIXTURE_STOCK_CODE): [
            {
                "result_id": FIXTURE_RESULT_ID,
                "stock_code": FIXTURE_STOCK_CODE,
                "personalization_scope_id": FIXTURE_SCOPE_ID,
                "prediction_id": FIXTURE_PREDICTION_ID,
                "prediction_receipt_hash": receipt["receipt_hash"],
                "outcome_id": "outcome_fixture_001",
                "event_id": "event_fixture_001",
                "window_days": 20,
                "return_basis": FIXTURE_RETURN_BASIS,
                "label_contract_id": FIXTURE_LABEL_CONTRACT_ID,
                "cost_scenario_hash": FIXTURE_COST_HASH,
                "label_available_at": "2025-03-02T00:00:00+00:00",
                "outcome_recorded_at": "2025-03-02T00:00:00+00:00",
                "outcome_status": "ready",
                "outcome_tier": "natural_forward",
                "forward_return_bp": 125,
            }
        ],
    }
    projection_service = PersonalizationProjectionService(
        recommendation_reader={FIXTURE_RESULT_ID: result},
        action_reader=action_reader,
        outcome_reader=outcome_reader,
    )
    projection = projection_service.build_for_candidate(
        result_id=FIXTURE_RESULT_ID,
        stock_code=FIXTURE_STOCK_CODE,
        personalization_scope_id=FIXTURE_SCOPE_ID,
        result=result,
        delivery_capture=delivered,
        projection_receipt=receipt,
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
    )
    missing_scope_result = deepcopy(result)
    missing_scope_result["run_context"].pop("personalization_delivery_captures")
    missing_scope = projection_service.build_for_candidate(
        result_id=FIXTURE_RESULT_ID,
        stock_code=FIXTURE_STOCK_CODE,
        personalization_scope_id=FIXTURE_SCOPE_ID,
        result=missing_scope_result,
        projection_receipt=receipt,
    )
    persisted_capture = capture_service.mark_persisted(
        generated,
        persisted_at="2025-02-10T08:55:00+00:00",
    )
    not_delivered_result = deepcopy(result)
    not_delivered_result["run_context"]["personalization_delivery_captures"] = [
        persisted_capture.to_dict()
    ]
    not_delivered = projection_service.build_for_candidate(
        result_id=FIXTURE_RESULT_ID,
        stock_code=FIXTURE_STOCK_CODE,
        personalization_scope_id=FIXTURE_SCOPE_ID,
        result=not_delivered_result,
        delivery_capture=persisted_capture,
        projection_receipt=receipt,
    )
    invalid_receipt = dict(receipt)
    invalid_receipt["receipt_hash"] = "sha256:" + ("9" * 64)
    bad_receipt = projection_service.build_for_candidate(
        result_id=FIXTURE_RESULT_ID,
        stock_code=FIXTURE_STOCK_CODE,
        personalization_scope_id=FIXTURE_SCOPE_ID,
        result=result,
        delivery_capture=delivered,
        projection_receipt=invalid_receipt,
    )

    fit_rows = _fixture_rows()
    policy = PersonalizationCalibrationPolicy(
        horizon_days=20,
        cost_scenario_hash=FIXTURE_COST_HASH,
        shrinkage_strength=2,
        universe_policy_hash="sha256:" + ("3" * 64),
        label_contract_id=FIXTURE_LABEL_CONTRACT_ID,
        scope_id=FIXTURE_SCOPE_ID,
        source_id="recommendation_service",
        model_id="model_fixture_v1",
        dataset_id="dataset_fixture_v1",
        dataset_hash=FIXTURE_DATASET_HASH,
        return_basis=FIXTURE_RETURN_BASIS,
    )
    evaluator = PersonalizationCalibrationEvaluator()
    artifact = evaluator.fit(
        fit_rows,
        fit_as_of="2025-01-31",
        policy=policy,
        artifact_id="personalization_fit_fixture_001",
        created_at="2025-02-01T00:00:00+00:00",
    )
    evaluation = evaluator.evaluate(
        artifact,
        _fixture_evaluation_rows(),
        evaluated_as_of="2025-03-20",
        evaluation_cutoff_at="2025-03-20T00:00:00+00:00",
    )
    projection_dict = projection.to_dict()
    evaluation_dict = evaluation.to_dict()
    payload: dict[str, Any] = {
        "schema_version": RUNNER_RECEIPT_SCHEMA_VERSION,
        "runner": "inspect_personalization_contract",
        "mode": "fixture",
        "bounded": True,
        "shadow_only": True,
        "formal_order_allowed": False,
        "auto_action_allowed": False,
        "natural_forward_credit": False,
        "adoption_confidence_status": evaluation.adoption_confidence_status,
        "decision": evaluation.decision,
        "reason": evaluation.reason,
        "counts": {
            "projection_linked_prediction": int(projection.status == "linked_prediction"),
            "projection_not_delivered": int(projection.status == "not_delivered"),
            "projection_duplicate_exact": projection.duplicate_exact_count,
            "projection_duplicate_conflict": projection.duplicate_conflict_count,
            "natural_outcome_rows": sum(
                1
                for item in projection.outcomes
                if str(item.get("outcome_tier") or "") == "natural_forward"
                and str(item.get("outcome_status") or "") == "ready"
            ),
            "calibration_fit_rows": artifact.fit_row_count,
            "calibration_evaluation_rows": len(evaluation.rows),
            "calibration_valid_rows": int(evaluation.baseline_metrics.get("sample_count") or 0),
        },
        "metrics": {
            "baseline": dict(evaluation.baseline_metrics),
            "personal_challenger": dict(evaluation.personal_challenger_metrics),
        },
        "projection": projection_dict,
        "negative_cases": {
            "missing_scope": missing_scope.status,
            "persisted_not_delivered": not_delivered.status,
            "invalid_receipt": bad_receipt.status,
        },
        "calibration": evaluation_dict,
        "hashes": {
            "scope_envelope_hash": scope.envelope_hash,
            "capture_hash": delivered.capture_hash,
            "projection_receipt_hash": receipt["receipt_hash"],
            "fit_row_fingerprint": artifact.fit_row_fingerprint,
            "evaluation_row_fingerprint": evaluation.evaluation_row_fingerprint,
            "policy_hash": policy.policy_hash,
        },
        "warnings": [
            "fixture_only_no_formal_selection",
            "adoption_not_evaluable",
            "natural_forward_credit_disabled",
        ],
    }
    payload["runner_receipt_hash"] = canonical_payload_hash(payload)
    return payload


def _write_create_only(path: Path, payload: bytes) -> None:
    path = path.expanduser().resolve()
    if path.is_symlink():
        raise RuntimeError("runner output path must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        existing = path.read_bytes()
        if existing != payload:
            raise RuntimeError("runner output exists with a different payload")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="store_true", help="執行 deterministic in-memory fixture")
    parser.add_argument("--output", type=Path, help="以 create-only 寫入 runner receipt JSON")
    args = parser.parse_args(argv)
    if not args.fixture:
        parser.error("目前 first slice 僅提供 --fixture；不會連接正式資料或 scheduler")
    receipt = run_fixture()
    encoded = (json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if args.output is not None:
        _write_create_only(args.output, encoded)
    print(encoded.decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
