"""個人已保存推薦捕獲的 canonical receipt/readback 測試。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

import pytest

import app_module.recommendation.personal_prediction_capture as capture_module
from app_module.recommendation.contracts import ExecutionEvent
from app_module.recommendation.personal_prediction_capture import (
    MAX_PERSONAL_CAPTURE_FILE_BYTES,
    MAX_PERSONAL_CAPTURE_RECEIPT_BYTES,
    PersonalPredictionCaptureError,
    capture_personal_saved_result,
    read_personal_prediction_capture,
    _taipei_decision_date,
)
from app_module.recommendation.personal_use_policy import (
    PERSONAL_CALIBRATED_PROBABILITY_MODE,
    PERSONAL_USE_POLICY_SCHEMA_V1,
    PERSONAL_USE_POLICY_VERSION,
    PERSONAL_USE_POLICY_SCHEMA_V2,
    PERSONAL_USE_POLICY_VERSION_V2,
    PersonalSourceFileIdentityV1,
    PersonalSourceReplayScopeV1,
    PersonalSourceTimeTrustV1,
    PersonalCalibrationCandidateV1,
    validate_personal_use_policy_snapshot,
    _policy_hash,
)
from ml_module.recommendation_inference_provenance import (
    RecommendationProvenanceError,
    read_inference_projection_receipt,
)
from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario


_DECISION_AT = datetime(2025, 5, 1, 12, 0, tzinfo=timezone.utc)
_RECEIPT_CREATED_AT = datetime(2025, 5, 1, 12, 1, tzinfo=timezone.utc)
_PERSISTED_AT = datetime(2025, 5, 1, 12, 2, tzinfo=timezone.utc)


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _build_case(
    tmp_path: Path,
    *,
    include_policy: bool = True,
    policy_v2: bool = False,
):
    # 重用 C1 已核過的真實 receipt builder 與 canonical query stack。
    from tests.test_c1_ml_abi_receipt_readiness import (
        _query_stack,
        _synthetic_receipt,
    )

    execution, receipt, receipt_path = _synthetic_receipt(tmp_path / "shadow")
    candidate_identity = dict(receipt.payload["candidate_identity"])
    candidate_root = Path(str(candidate_identity["candidate_root"]))
    candidate_json_path = candidate_root / "candidate.json"
    candidate_payload = json.loads(candidate_json_path.read_text(encoding="utf-8"))
    from ml_module.recommendation_calibration_training import candidate_freeze_hash
    import ml_module.recommendation_inference_provenance as provenance

    freeze_hash = candidate_freeze_hash(
        candidate_id=str(candidate_identity["candidate_id"]),
        dataset_hash=str(candidate_identity["dataset_hash"]),
        manifest_hash=str(candidate_identity["candidate_manifest_hash"]),
        artifact_hash=str(candidate_identity["candidate_artifact_hash"]),
        evaluation={},
    )
    candidate_payload["candidate_freeze_hash"] = freeze_hash
    candidate_json_path.write_text(
        json.dumps(candidate_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    candidate_json_hash = "sha256:" + hashlib.sha256(candidate_json_path.read_bytes()).hexdigest()
    candidate_identity["candidate_freeze_hash"] = freeze_hash
    complete_projections = tuple(
        {
            **dict(row),
            "calibrated_probability_bp": 6_500 if row["stock_code"] == "1101" else 7_200,
            "calibrated_probability_status": "active_effective",
        }
        for row in receipt.payload["projections"]
    )
    updated_receipt = provenance.build_inference_projection_receipt(
        decision_date=str(receipt.payload["decision_date"]),
        result_id=str(receipt.payload["result_id"]),
        candidate_identity=candidate_identity,
        training_provenance=receipt.payload["training_provenance"],
        inference_provenance=receipt.payload["inference_provenance"],
        compatibility=receipt.payload["provenance_compatibility"],
        projections=complete_projections,
        selection_contract=receipt.payload["selection_contract"],
    )
    receipt_hash = updated_receipt.receipt_hash
    receipt_path = provenance.persist_inference_projection_receipt(
        receipt_path.parents[3], updated_receipt
    )
    binding = replace(
        execution.ml_receipt_refs[0],
        receipt_ref=replace(execution.ml_receipt_refs[0].receipt_ref, reference_id=str(receipt_path)),
        receipt_hash=receipt_hash,
    )
    projection_ref = replace(
        execution.ml_projection_refs[0],
        reference_id=str(updated_receipt.payload["projection_rows_sha256"]),
    )
    execution = replace(
        execution,
        ml_receipt_refs=(binding,),
        ml_projection_refs=(projection_ref,),
    )
    receipt = updated_receipt
    candidate = PersonalCalibrationCandidateV1(
        candidate_id=str(candidate_identity["candidate_id"]),
        candidate_root=str(candidate_identity["candidate_root"]),
        candidate_json_sha256=candidate_json_hash,
        candidate_manifest_hash=str(candidate_identity["candidate_manifest_hash"]),
        candidate_artifact_hash=str(candidate_identity["candidate_artifact_hash"]),
        candidate_freeze_hash=str(candidate_identity["candidate_freeze_hash"]),
        dataset_hash=str(candidate_identity["dataset_hash"]),
    )
    if policy_v2:
        confirmed_at = "2025-04-30T00:00:00.000000Z"
        source_trust = PersonalSourceTimeTrustV1(
            source_database_path=str((tmp_path / "declared-source.sqlite").resolve()),
            file_identity=PersonalSourceFileIdentityV1(device=1, inode=2),
            source_database_size_bytes=128,
            source_slice_sha256="sha256:" + hashlib.sha256(b"test-source-slice").hexdigest(),
            candidate=candidate,
            replay_scope=PersonalSourceReplayScopeV1(
                dataset_ids=("test-dataset",),
                decision_dates=("2025-04-29",),
                symbols=("1101",),
                sample_count=1,
            ),
            confirmed_at=confirmed_at,
        )
        policy_body = {
            "schema_version": PERSONAL_USE_POLICY_SCHEMA_V2,
            "policy_version": PERSONAL_USE_POLICY_VERSION_V2,
            "revision": 1,
            "scope_id": "local-test-profile",
            "mode": PERSONAL_CALIBRATED_PROBABILITY_MODE,
            "confirmed_at": confirmed_at,
            "candidate": candidate.to_dict(),
            "source_time_trust": source_trust.to_dict(),
        }
    else:
        policy_body = {
            "schema_version": PERSONAL_USE_POLICY_SCHEMA_V1,
            "policy_version": PERSONAL_USE_POLICY_VERSION,
            "revision": 1,
            "scope_id": "local-test-profile",
            "mode": PERSONAL_CALIBRATED_PROBABILITY_MODE,
            "confirmed_at": "2025-04-30T00:00:00.000000Z",
            "candidate": candidate.to_dict(),
        }
    policy_snapshot = {
        **policy_body,
        "policy_sha256": _policy_hash(policy_body),
    }
    policy_snapshot = validate_personal_use_policy_snapshot(policy_snapshot)

    event_details = {
        "schema_version": (
            "recommendation-personal-use-policy-snapshot.v2"
            if policy_v2
            else "recommendation-personal-use-policy-snapshot.v1"
        ),
        "result_id": execution.result_id,
        "decision_at": _DECISION_AT.isoformat(),
        "policy_snapshot": policy_snapshot,
        "requested_mode": PERSONAL_CALIBRATED_PROBABILITY_MODE,
        "effective_mode": PERSONAL_CALIBRATED_PROBABILITY_MODE,
    }
    if policy_v2:
        event_details.update(
            {
                "source_time_basis": "user_declared_source_time",
                "research_only": True,
                "official_historical_pit_verified": False,
            }
        )
    events = []
    if include_policy:
        events.append(
            ExecutionEvent(
                event_type="personal_use_policy_snapshot",
                message="合成個人政策快照",
                occurred_at=_DECISION_AT,
                details=event_details,
            )
        )

    payload = receipt.payload
    inference = payload["inference_provenance"]
    events.append(
        ExecutionEvent(
            event_type="ml_projection_receipt_capture",
            message="合成已驗證 receipt 讀回",
            occurred_at=_RECEIPT_CREATED_AT,
            details={
                "attempted": True,
                "persisted": True,
                "readback_verified": True,
                "identity_verified": True,
                "path": str(receipt_path.resolve()),
                "receipt_hash": receipt.receipt_hash,
                "receipt_created_at": _RECEIPT_CREATED_AT.isoformat(),
                "error": "",
                "result_id": execution.result_id,
                "decision_date": payload["decision_date"],
                "candidate_id": candidate.candidate_id,
                "candidate_identity": payload["candidate_identity"],
                "cost_scenario_hash": payload["cost_scenario_hash"],
                "cost_scenario_id": inference["cost_scenario_id"],
                "projected_stock_codes": tuple(
                    row["stock_code"] for row in payload["projections"]
                ),
                "projection_rows_sha256": payload["projection_rows_sha256"],
                "inference_source_hash": inference["inference_source_hash"],
                "inference_pit_hash": inference["inference_pit_hash"],
                "feature_rows_sha256": inference["feature_rows_sha256"],
                "receipt_body_hash_verified": True,
            },
        )
    )
    execution = replace(
        execution,
        context=replace(execution.context, decision_at=_DECISION_AT),
        events=tuple(events),
    )
    persistence, queries = _query_stack(tmp_path / "canonical")
    persistence.save(execution, now=lambda: _PERSISTED_AT)
    return execution, receipt, receipt_path, persistence, queries, policy_snapshot


def test_personal_capture_uses_canonical_receipt_readback_and_is_create_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution, receipt, receipt_path, _persistence, queries, _policy = _build_case(
        tmp_path
    )
    receipt_before = receipt_path.read_bytes()
    original_builder = queries._canonical_read_model

    def original_two_argument_call_shape(record: Any, envelope: Any) -> Any:
        return original_builder(record, envelope)

    with monkeypatch.context() as patch:
        patch.setattr(queries, "_canonical_read_model", original_two_argument_call_shape)
        original = queries.get(execution.result_id)
    assert original is not None
    assert original.ml_read_status == "verified"
    original_payload_hash = original.payload_hash
    bounded = queries.get(
        execution.result_id,
        max_receipt_bytes=MAX_PERSONAL_CAPTURE_RECEIPT_BYTES,
    )
    assert bounded is not None
    assert bounded.ml_read_status == "verified"
    assert bounded.ml_projection_rows == original.ml_projection_rows

    import ml_module.recommendation_inference_provenance as provenance

    def no_inference(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("個人捕獲不得重新推論或重建 receipt")

    monkeypatch.setattr(provenance, "build_inference_provenance", no_inference)
    monkeypatch.setattr(provenance, "build_inference_projection_receipt", no_inference)
    monkeypatch.setattr(provenance, "persist_inference_projection_receipt", no_inference)

    personal_root = tmp_path / "personal-profile"
    captured = capture_personal_saved_result(
        execution.result_id,
        queries,
        personal_root,
    )
    assert captured.idempotent is False
    assert captured.path.is_file()
    assert personal_root in captured.path.parents
    assert receipt_path.read_bytes() == receipt_before
    assert captured.decision_at == "2025-05-01T12:00:00.000000Z"
    assert captured.persisted_at == "2025-05-01T12:02:00.000000Z"
    assert captured.capture_written_at > captured.persisted_at

    payload = read_personal_prediction_capture(
        captured.path,
        queries,
        personal_root,
        expected_result_id=execution.result_id,
    )
    assert payload["schema_version"] == "recommendation-personal-prediction-capture.v1"
    assert payload["capture_origin"] == "personal_saved_result"
    assert payload["receipt_binding"]["receipt_hash"] == receipt.receipt_hash
    assert [row["stock_code"] for row in payload["delivered_rows"]] == [
        item.stock_code for item in execution.decision.items
    ]
    assert all(
        type(row["projection"]["calibrated_probability_bp"]) is int
        for row in payload["delivered_rows"]
    )

    bytes_before_retry = captured.path.read_bytes()
    retry = capture_personal_saved_result(
        execution.result_id,
        queries,
        personal_root,
    )
    assert retry.idempotent is True
    assert retry.path == captured.path
    assert retry.payload_sha256 == captured.payload_sha256
    assert captured.path.read_bytes() == bytes_before_retry

    after = queries.get(execution.result_id)
    assert after is not None
    assert after.payload_hash == original_payload_hash
    assert after.execution == execution


def test_personal_capture_v3_preserves_verified_v2_source_time_markers(
    tmp_path: Path,
) -> None:
    execution, _receipt, _receipt_path, _persistence, queries, policy = _build_case(
        tmp_path,
        policy_v2=True,
    )
    personal_root = tmp_path / "personal-profile"

    captured = capture_personal_saved_result(
        execution.result_id,
        queries,
        personal_root,
    )
    payload = read_personal_prediction_capture(
        captured.path,
        queries,
        personal_root,
        expected_result_id=execution.result_id,
    )

    # 此 fixture 沒有 baseline event，故外層維持 v1；policy event 自身版本為 v2。
    assert payload["schema_version"] == "recommendation-personal-prediction-capture.v1"
    event = payload["policy_event"]
    assert set(event) == {
        "schema_version",
        "result_id",
        "decision_at",
        "policy_snapshot",
        "requested_mode",
        "effective_mode",
        "source_time_basis",
        "research_only",
        "official_historical_pit_verified",
    }
    assert event["schema_version"] == "recommendation-personal-use-policy-snapshot.v2"
    assert event["policy_snapshot"] == policy
    assert event["source_time_basis"] == policy["source_time_trust"]["basis"]
    assert event["research_only"] is policy["source_time_trust"]["research_only"] is True
    assert (
        event["official_historical_pit_verified"]
        is policy["source_time_trust"]["official_historical_pit_verified"]
        is False
    )


def test_personal_capture_v3_rejects_rehashed_v2_source_marker_tamper(
    tmp_path: Path,
) -> None:
    execution, _receipt, _receipt_path, _persistence, queries, _policy = _build_case(
        tmp_path,
        policy_v2=True,
    )
    personal_root = tmp_path / "personal-profile"
    captured = capture_personal_saved_result(
        execution.result_id,
        queries,
        personal_root,
    )
    payload = json.loads(captured.path.read_text(encoding="utf-8"))
    payload["policy_event"]["research_only"] = False
    body = dict(payload)
    body.pop("payload_sha256")
    payload["payload_sha256"] = capture_module._payload_hash(body)
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    captured.path.write_bytes(encoded)

    with pytest.raises(PersonalPredictionCaptureError, match="來源時間標記"):
        read_personal_prediction_capture(
            captured.path,
            queries,
            personal_root,
            expected_result_id=execution.result_id,
        )


def test_v3_baseline_accepts_ranked_delivery_order_and_rejects_membership_change() -> None:
    projected_codes = ["2408", "2454", "3037"]
    delivered_codes = ["2454", "2408", "3037"]
    candidate_id = "personal-candidate-ordering"
    scenario = build_legacy_cost_scenario(50)
    scenario_payload = scenario.to_dict(include_hash=True)
    receipt_binding = {
        "receipt_hash": _sha256(b"receipt"),
        "projection_rows_sha256": _sha256(b"projection-rows"),
        "cost_scenario_hash": scenario.scenario_hash,
        "projected_stock_codes": projected_codes,
        "candidate_id": candidate_id,
    }

    def _make_snapshot(codes: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        projections = [
            {
                "stock_code": code,
                "projection": {
                    "status": "active_candidate",
                    "calibrated_probability_status": "active_effective",
                    "model_version": candidate_id,
                    "calibrated_probability_bp": 6_000,
                    "after_cost_profit_probability_bp": None,
                    "cost_scenario_id": scenario.scenario_id,
                    "cost_scenario_version": scenario.scenario_version,
                    "cost_scenario_hash": scenario.scenario_hash,
                    "cost_basis": scenario.cost_basis,
                    "cost_basis_bp": scenario.fixed_round_trip_cost_bp,
                    "cost_policy_id": scenario.policy_id,
                    "cost_policy_version": scenario.policy_version,
                    "policy_estimate_date": scenario.policy_estimate_date,
                    "research_order_amount_twd": scenario_payload[
                        "research_order_amount_twd"
                    ],
                    "research_order_quantity_shares": scenario.research_order_quantity_shares,
                    "lot_type": scenario.lot_type,
                    "instrument_type": scenario.instrument_type,
                },
            }
            for code in codes
        ]
        snapshot: dict[str, Any] = {
            "schema_version": capture_module.PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V2,
            "result_id": "personal-ordering-result",
            "decision_at": "2025-05-01T12:00:00.000000Z",
            "decision_date": "2025-05-01",
            "receipt_hash": receipt_binding["receipt_hash"],
            "projection_rows_sha256": receipt_binding["projection_rows_sha256"],
            "cost_scenario_hash": receipt_binding["cost_scenario_hash"],
            "projected_stock_codes": projected_codes,
            "upside_baseline_kind": "fixed_null_benchmark_50pct",
            "upside_baseline_id": "null_benchmark_50pct_v1",
            "upside_probability_bp_by_symbol": {
                code: 5_000 for code in projected_codes
            },
            "after_cost_baseline_status": "unavailable",
            "after_cost_baseline_id": None,
            "after_cost_probability_bp_by_symbol": {
                code: None for code in projected_codes
            },
            "delivered_stock_codes": list(delivered_codes),
            "model_active_stock_codes": projected_codes,
            "rule_only_fallback_stock_codes": [],
            "delivered_count": len(delivered_codes),
            "model_active_count": len(projected_codes),
            "fallback_count": 0,
            "model_coverage_bp": 10_000,
            "cost_scenario": scenario_payload,
        }
        snapshot["snapshot_sha256"] = _sha256(
            capture_module._canonical_json_bytes(snapshot)
        )
        return snapshot, projections

    snapshot, rows = _make_snapshot(delivered_codes)
    verified = capture_module._validate_probability_baseline_snapshot(
        snapshot,
        result_id="personal-ordering-result",
        decision_at="2025-05-01T12:00:00.000000Z",
        decision_date="2025-05-01",
        receipt_binding=receipt_binding,
        delivered_rows=rows,
    )
    assert verified["projected_stock_codes"] == projected_codes
    assert verified["delivered_stock_codes"] == delivered_codes

    wrong_delivery_order, canonical_rows = _make_snapshot(delivered_codes)
    wrong_delivery_order["delivered_stock_codes"] = list(reversed(delivered_codes))
    wrong_delivery_body = {
        key: value
        for key, value in wrong_delivery_order.items()
        if key != "snapshot_sha256"
    }
    wrong_delivery_order["snapshot_sha256"] = _sha256(
        capture_module._canonical_json_bytes(wrong_delivery_body)
    )
    with pytest.raises(ValueError, match="ordered partition"):
        capture_module._validate_probability_baseline_snapshot(
            wrong_delivery_order,
            result_id="personal-ordering-result",
            decision_at="2025-05-01T12:00:00.000000Z",
            decision_date="2025-05-01",
            receipt_binding=receipt_binding,
            delivered_rows=canonical_rows,
        )

    mismatched, mismatched_rows = _make_snapshot(["2408", "2454", "9999"])
    mismatched["delivered_stock_codes"] = ["2408", "2454", "9999"]
    with pytest.raises(ValueError, match="active/fallback partition"):
        capture_module._validate_probability_baseline_snapshot(
            mismatched,
            result_id="personal-ordering-result",
            decision_at="2025-05-01T12:00:00.000000Z",
            decision_date="2025-05-01",
            receipt_binding=receipt_binding,
            delivered_rows=mismatched_rows,
        )

    malformed, malformed_rows = _make_snapshot(delivered_codes)
    malformed["delivered_stock_codes"] = [{"not": "a stock code"}, "2408", "3037"]
    malformed_body = {
        key: value for key, value in malformed.items() if key != "snapshot_sha256"
    }
    malformed["snapshot_sha256"] = _sha256(
        capture_module._canonical_json_bytes(malformed_body)
    )
    with pytest.raises(ValueError, match="active/fallback partition"):
        capture_module._validate_probability_baseline_snapshot(
            malformed,
            result_id="personal-ordering-result",
            decision_at="2025-05-01T12:00:00.000000Z",
            decision_date="2025-05-01",
            receipt_binding=receipt_binding,
            delivered_rows=malformed_rows,
        )


def test_capture_failure_keeps_canonical_result_and_does_not_write_personal_bytes(
    tmp_path: Path,
) -> None:
    execution, _receipt, _receipt_path, _persistence, queries, _policy = _build_case(
        tmp_path,
        include_policy=False,
    )
    before = queries.get(execution.result_id)
    assert before is not None
    personal_root = tmp_path / "personal-profile"

    with pytest.raises(PersonalPredictionCaptureError, match="政策快照"):
        capture_personal_saved_result(execution.result_id, queries, personal_root)

    after = queries.get(execution.result_id)
    assert after is not None
    assert after.payload_hash == before.payload_hash
    assert after.execution == before.execution
    assert not personal_root.exists()


def test_personal_capture_file_cap_is_checked_before_json_decode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, _receipt, _receipt_path, _persistence, queries, _policy = _build_case(
        tmp_path
    )
    personal_root = tmp_path / "personal-profile"
    captured = capture_personal_saved_result(
        execution.result_id,
        queries,
        personal_root,
    )
    with captured.path.open("r+b") as stream:
        stream.truncate(MAX_PERSONAL_CAPTURE_FILE_BYTES + 1)

    json_loads_calls: list[object] = []
    original_loads = capture_module.json.loads

    def track_json_loads(payload: str | bytes | bytearray, *args: Any, **kwargs: Any) -> Any:
        json_loads_calls.append(payload)
        return original_loads(payload, *args, **kwargs)

    monkeypatch.setattr(capture_module.json, "loads", track_json_loads)
    with pytest.raises(PersonalPredictionCaptureError, match="大小上限"):
        capture_module._read_capture_file(captured.path, root=personal_root)
    assert json_loads_calls == []


def test_personal_capture_file_replacement_during_read_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, _receipt, _receipt_path, _persistence, queries, _policy = _build_case(
        tmp_path
    )
    personal_root = tmp_path / "personal-profile"
    captured = capture_personal_saved_result(
        execution.result_id,
        queries,
        personal_root,
    )
    replacement = captured.path.with_name("replacement.json")
    replacement.write_bytes(captured.path.read_bytes())
    original_reader = capture_module._read_regular_file_no_follow

    def replace_after_open(
        path: Path,
        root: Path,
        *,
        max_bytes: int | None = None,
    ) -> bytes:
        raw = original_reader(path, root, max_bytes=max_bytes)
        replacement.replace(path)
        return raw

    monkeypatch.setattr(
        capture_module,
        "_read_regular_file_no_follow",
        replace_after_open,
    )
    with pytest.raises(PersonalPredictionCaptureError, match="路徑身份改變"):
        capture_module._read_capture_file(captured.path, root=personal_root)


def test_personal_capture_bounds_receipt_before_json_decode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, _receipt, receipt_path, _persistence, queries, _policy = _build_case(
        tmp_path
    )
    original = queries.get(execution.result_id)
    assert original is not None
    assert original.ml_read_status == "verified"
    original_payload_hash = original.payload_hash

    # Sparse extension crosses the cap. A bounded reader must reject from the
    # opened file size before attempting to decode the payload.
    with receipt_path.open("r+b") as stream:
        stream.truncate(MAX_PERSONAL_CAPTURE_RECEIPT_BYTES + 1)

    import ml_module.recommendation_inference_provenance as provenance

    json_loads_calls: list[object] = []
    original_loads = provenance.json.loads

    def track_json_loads(
        payload: str | bytes | bytearray,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        json_loads_calls.append(payload)
        return original_loads(payload, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(provenance.json, "loads", track_json_loads)
        with pytest.raises(RecommendationProvenanceError, match="byte limit"):
            read_inference_projection_receipt(
                receipt_path,
                expected_receipt_hash=execution.ml_receipt_refs[0].receipt_hash,
                max_receipt_bytes=MAX_PERSONAL_CAPTURE_RECEIPT_BYTES,
            )
    assert json_loads_calls == []

    bounded_reads: list[int | None] = []
    original_bounded_reader = provenance._read_bounded_regular_file_no_follow

    def track_bounded_reader(path: Path, *, max_bytes: int) -> bytes:
        bounded_reads.append(max_bytes)
        return original_bounded_reader(path, max_bytes=max_bytes)

    monkeypatch.setattr(
        provenance,
        "_read_bounded_regular_file_no_follow",
        track_bounded_reader,
    )
    personal_root = tmp_path / "personal-profile"
    with pytest.raises(PersonalPredictionCaptureError, match="讀回上限"):
        capture_personal_saved_result(
            execution.result_id,
            queries,
            personal_root,
        )
    assert bounded_reads == [MAX_PERSONAL_CAPTURE_RECEIPT_BYTES]
    assert not personal_root.exists()

    after = queries.get(execution.result_id)
    assert after is not None
    assert after.payload_hash == original_payload_hash
    assert after.execution == original.execution


def test_bounded_receipt_reader_rejects_symlinked_path_components(
    tmp_path: Path,
) -> None:
    _execution, receipt, receipt_path, _persistence, _queries, _policy = _build_case(
        tmp_path
    )
    link_path = tmp_path / "receipt-link.json"
    try:
        link_path.symlink_to(receipt_path)
    except (NotImplementedError, OSError) as exc:
        if os.name != "nt":
            pytest.skip(f"此執行環境不能建立測試 symlink：{type(exc).__name__}")
        junction = tmp_path / "receipt-junction"
        completed = subprocess.run(
            [
                os.environ.get("COMSPEC", "cmd.exe"),
                "/c",
                "mklink",
                "/J",
                str(junction),
                str(receipt_path.parent),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode != 0:
            pytest.skip(
                "此執行環境不能建立 symlink/junction："
                f"{completed.stderr.strip() or completed.stdout.strip()}"
            )
        try:
            with pytest.raises(RecommendationProvenanceError):
                read_inference_projection_receipt(
                    junction / receipt_path.name,
                    expected_receipt_hash=receipt.receipt_hash,
                    expected_decision_date=str(receipt.payload["decision_date"]),
                    expected_candidate_id=str(
                        receipt.payload["candidate_identity"]["candidate_id"]
                    ),
                    expected_result_id=_execution.result_id,
                    expected_cost_scenario_hash=str(receipt.payload["cost_scenario_hash"]),
                    max_receipt_bytes=MAX_PERSONAL_CAPTURE_RECEIPT_BYTES,
                )
        finally:
            os.rmdir(junction)
    else:
        with pytest.raises(RecommendationProvenanceError):
            read_inference_projection_receipt(
                link_path,
                expected_receipt_hash=receipt.receipt_hash,
                expected_decision_date=str(receipt.payload["decision_date"]),
                expected_candidate_id=str(
                    receipt.payload["candidate_identity"]["candidate_id"]
                ),
                expected_result_id=_execution.result_id,
                expected_cost_scenario_hash=str(receipt.payload["cost_scenario_hash"]),
                max_receipt_bytes=MAX_PERSONAL_CAPTURE_RECEIPT_BYTES,
            )


def test_bounded_receipt_reader_rejects_receipt_changed_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _execution, receipt, receipt_path, _persistence, _queries, _policy = _build_case(
        tmp_path
    )

    import ml_module.recommendation_inference_provenance as provenance

    original_read = provenance._read_receipt_descriptor
    mutation_done = False

    def mutate_after_opened_read(
        descriptor: int,
        *,
        max_bytes: int,
    ) -> tuple[bytes, Any, Any]:
        nonlocal mutation_done
        result = original_read(descriptor, max_bytes=max_bytes)
        if not mutation_done:
            with receipt_path.open("ab") as stream:
                stream.write(b"changed-after-read")
            mutation_done = True
        return result

    monkeypatch.setattr(
        provenance,
        "_read_receipt_descriptor",
        mutate_after_opened_read,
    )
    with pytest.raises(RecommendationProvenanceError, match="changed during bounded read"):
        read_inference_projection_receipt(
            receipt_path,
            expected_receipt_hash=receipt.receipt_hash,
            max_receipt_bytes=MAX_PERSONAL_CAPTURE_RECEIPT_BYTES,
        )
    assert mutation_done is True


def test_personal_capture_readback_bounds_receipt_before_accepting_saved_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, _receipt, receipt_path, _persistence, queries, _policy = _build_case(
        tmp_path
    )
    personal_root = tmp_path / "personal-profile"
    captured = capture_personal_saved_result(
        execution.result_id,
        queries,
        personal_root,
    )
    capture_before = captured.path.read_bytes()
    with receipt_path.open("r+b") as stream:
        stream.truncate(MAX_PERSONAL_CAPTURE_RECEIPT_BYTES + 1)

    import ml_module.recommendation_inference_provenance as provenance

    bounded_reads: list[int | None] = []
    original_bounded_reader = provenance._read_bounded_regular_file_no_follow

    def track_bounded_reader(path: Path, *, max_bytes: int) -> bytes:
        bounded_reads.append(max_bytes)
        return original_bounded_reader(path, max_bytes=max_bytes)

    monkeypatch.setattr(
        provenance,
        "_read_bounded_regular_file_no_follow",
        track_bounded_reader,
    )
    with pytest.raises(PersonalPredictionCaptureError, match="讀回上限"):
        read_personal_prediction_capture(
            captured.path,
            queries,
            personal_root,
            expected_result_id=execution.result_id,
        )
    assert bounded_reads == [MAX_PERSONAL_CAPTURE_RECEIPT_BYTES]
    assert captured.path.read_bytes() == capture_before


def test_personal_root_cannot_overlap_learning_root(tmp_path: Path) -> None:
    execution, _receipt, receipt_path, _persistence, queries, _policy = _build_case(
        tmp_path
    )
    learning_root = receipt_path.parents[3]
    before = queries.get(execution.result_id)
    assert before is not None

    with pytest.raises(PersonalPredictionCaptureError, match="完全分離"):
        capture_personal_saved_result(
            execution.result_id,
            queries,
            learning_root / "personal-captures",
        )

    assert not (learning_root / "personal-captures").exists()
    after = queries.get(execution.result_id)
    assert after is not None
    assert after.payload_hash == before.payload_hash


def test_decision_date_uses_taipei_calendar_day_for_utc_clock_boundary() -> None:
    assert _taipei_decision_date(
        datetime(2026, 9, 26, 18, 30, tzinfo=timezone.utc)
    ) == date(2026, 9, 27)
