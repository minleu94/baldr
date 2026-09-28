from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.personalization_contract import (
    PersonalRecommendationChoice,
    PersonalRecommendationModelEvidence,
    PersonalRecommendationOverrideReason,
    canonical_payload_hash,
)
from app_module.personalization_action_recorder import (
    PersonalizationDecisionRecorder,
    PersonalizationDecisionRecorderError,
)
from app_module.journal_service import JournalService
from app_module.personalization_read_service import (
    PersonalizationReadService,
    ReadOnlyEvidenceSource,
    ReadOnlyJournalRevisionSource,
    ReadOnlyRecommendationSource,
)
from app_module.recommendation.codec import (
    ExecutionReadEnvelope,
    decode_execution_envelope,
    encode_execution,
)
from app_module.recommendation.contracts import (
    Context,
    ExecutionEvent,
    ExecutionStatus,
    MLAvailability,
    MLAvailabilityStatus,
    MLReceiptBinding,
    RecommendationUniverseIdentity,
    RecommendationExecution,
    ReferenceKind,
    Request,
    UniversePolicyIdentity,
    UniverseSnapshotIdentity,
    VersionReference,
)
from app_module.recommendation.queries import RecommendationExecutionQueries
from app_module.recommendation_calibration_consumer import (
    RecommendationCalibrationProjection,
)
from data_module.result_artifact_store import (
    ArtifactIndexMetadata,
    ArtifactIndexRecord,
)
from decision_module.recommendation.contracts import (
    DecisionBatch,
    RecommendationItem,
)
from decision_module.recommendation.contracts import UniverseReference
from app_module.recommendation.personal_use_policy import (
    PersonalCalibrationCandidateV1,
    RecommendationPersonalUsePolicyV1,
)


_HASH_A = "sha256:" + "a" * 64
_HASH_B = "sha256:" + "b" * 64
_HASH_C = "sha256:" + "c" * 64


def _policy_snapshot(*, mode: str = "rule_only") -> dict[str, object]:
    if mode == "rule_only":
        return RecommendationPersonalUsePolicyV1.default_rule_only(
            "local-profile"
        ).to_dict()
    if mode != "personal_calibrated_probability":
        raise ValueError("test policy mode is unsupported")
    candidate = PersonalCalibrationCandidateV1(
        candidate_id="candidate-2026-09-14",
        candidate_root="C:/isolated/candidate",
        candidate_json_sha256=_HASH_A,
        candidate_manifest_hash=_HASH_B,
        candidate_artifact_hash=_HASH_C,
        candidate_freeze_hash=_HASH_A,
        dataset_hash=_HASH_B,
    )
    body: dict[str, object] = {
        "schema_version": "recommendation-personal-use-policy.v1",
        "policy_version": 1,
        "revision": 1,
        "scope_id": "local-profile",
        "mode": mode,
        "confirmed_at": "2026-09-27T12:00:00.000000Z",
        "candidate": candidate.to_dict(),
    }
    return {**body, "policy_sha256": canonical_payload_hash(body)}


def _choice(**overrides: object) -> PersonalRecommendationChoice:
    values: dict[str, object] = {
        "result_id": "recommendation-20260927-001",
        "stock_code": "2330",
        "decision_date": "2026-09-27",
        "source_snapshot_id": "universe-20260927-001",
        "source_snapshot_hash": _HASH_C,
        "canonical_payload_hash": _HASH_A,
        "raw_artifact_sha256": _HASH_B,
        "choice": "adopt",
        "requested_mode": "rule_only",
        "effective_mode": "rule_only",
        "action_at": "2026-09-27T12:00:00+00:00",
        "recorded_at": "2026-09-27T12:00:00+00:00",
        "request_id": "choice-request-001",
        "policy_snapshot": _policy_snapshot(),
    }
    values.update(overrides)
    return PersonalRecommendationChoice(**values)  # type: ignore[arg-type]


def test_personal_choice_roundtrips_with_exact_schema_and_saved_policy() -> None:
    choice = _choice()

    encoded = choice.to_dict()
    decoded = PersonalRecommendationChoice.from_mapping(encoded)

    assert decoded == choice
    assert encoded["schema_version"] == "personal-recommendation-choice.v1"
    assert encoded["policy_snapshot"] == _policy_snapshot()
    assert encoded["choice_hash"] == choice.choice_hash


def test_personal_choice_requires_structured_reason_only_for_override() -> None:
    with pytest.raises(ValueError, match="override requires"):
        _choice(choice="override")

    override = _choice(
        choice="override",
        override_reason=PersonalRecommendationOverrideReason(
            code="new_information", detail="公司公告改變了原先判斷。"
        ),
    )
    assert override.to_dict()["override_reason"] == {
        "code": "new_information",
        "detail": "公司公告改變了原先判斷。",
    }
    with pytest.raises(ValueError, match="override requires"):
        _choice(
            override_reason=PersonalRecommendationOverrideReason(
                code="new_information", detail="不應附在一般採用事件。"
            )
        )


def test_personal_model_choice_requires_same_stock_date_and_effective_projection() -> None:
    evidence = PersonalRecommendationModelEvidence(
        candidate_id="candidate-2026-09-14",
        candidate_root="C:/isolated/candidate",
        candidate_json_sha256=_HASH_A,
        candidate_manifest_hash=_HASH_B,
        candidate_artifact_hash=_HASH_C,
        candidate_freeze_hash=_HASH_A,
        dataset_hash=_HASH_B,
        receipt_reference="C:/qa/receipts/receipt.json",
        receipt_hash=_HASH_A,
        projection_reference=_HASH_B,
        projection_rows_sha256=_HASH_B,
        stock_code="2330",
        decision_date="2026-09-27",
        model_version="candidate-2026-09-14",
        ranking_score_bp=7200,
        calibrated_probability_bp=6400,
        calibrated_probability_status="active_effective",
        cost_scenario_hash=_HASH_C,
    )
    choice = _choice(
        requested_mode="personal_calibrated_probability",
        effective_mode="personal_calibrated_probability",
        model_evidence=evidence,
        policy_snapshot=_policy_snapshot(mode="personal_calibrated_probability"),
    )

    assert PersonalRecommendationChoice.from_mapping(choice.to_dict()) == choice

    with pytest.raises(ValueError, match="must match selected stock"):
        _choice(
            requested_mode="personal_calibrated_probability",
            effective_mode="personal_calibrated_probability",
            model_evidence=replace(evidence, stock_code="1101"),
            policy_snapshot=_policy_snapshot(mode="personal_calibrated_probability"),
        )
    with pytest.raises(ValueError, match="effective saved projection"):
        replace(evidence, calibrated_probability_status="shadow_candidate")
    with pytest.raises(ValueError, match="candidate_artifact_hash differs"):
        _choice(
            requested_mode="personal_calibrated_probability",
            effective_mode="personal_calibrated_probability",
            model_evidence=replace(evidence, candidate_artifact_hash=_HASH_A),
            policy_snapshot=_policy_snapshot(mode="personal_calibrated_probability"),
        )


def test_personal_choice_rejects_today_policy_hash_substitution_and_old_schema() -> None:
    # 用完整 revision-1 candidate policy 起始，避免把固定 revision-0
    # rule-only 身分錯誤當成一般 hash-tamper 測例。
    policy = _policy_snapshot(mode="personal_calibrated_probability")
    policy["policy_sha256"] = _HASH_C
    with pytest.raises(ValueError, match="versioned schema/hash"):
        _choice(
            requested_mode="personal_calibrated_probability",
            policy_snapshot=policy,
        )

    encoded = _choice().to_dict()
    encoded["schema_version"] = "personalization-action.v1"
    with pytest.raises(ValueError, match="unsupported personal recommendation choice schema"):
        PersonalRecommendationChoice.from_mapping(encoded)


def test_personal_choice_does_not_infer_policy_for_legacy_saved_result() -> None:
    with pytest.raises(ValueError, match="requires a policy snapshot"):
        _choice(policy_snapshot=None)


def _model_receipt_case(rows: list[dict[str, object]]):
    policy = _policy_snapshot(mode="personal_calibrated_probability")
    candidate = policy["candidate"]
    assert isinstance(candidate, dict)
    receipt_path = Path("C:/isolated/receipts/model-receipt.json").resolve()
    receipt_payload = {
        "result_id": "recommendation-20260927-001",
        "decision_date": "2026-09-27",
        "cost_scenario_hash": _HASH_C,
        "candidate_identity": {
            key: candidate[key]
            for key in (
                "candidate_id",
                "candidate_root",
                "candidate_manifest_hash",
                "candidate_artifact_hash",
                "candidate_freeze_hash",
                "dataset_hash",
            )
        },
        "projection_rows_sha256": _HASH_B,
        "projections": rows,
    }
    binding = SimpleNamespace(
        model_candidate_id=candidate["candidate_id"],
        result_id="recommendation-20260927-001",
        decision_date=date(2026, 9, 27),
        projected_stock_codes=tuple(str(row["stock_code"]) for row in rows),
        cost_scenario_hash=_HASH_C,
        receipt_hash=_HASH_A,
        receipt_ref=SimpleNamespace(reference_id=str(receipt_path)),
    )
    execution = SimpleNamespace(
        ml_receipt_refs=(binding,),
        ml_projection_refs=(SimpleNamespace(reference_id=_HASH_B),),
    )
    read_model = SimpleNamespace(
        result_id="recommendation-20260927-001",
        ml_read_status="verified",
        ml_projection_rows=tuple(rows),
    )
    receipt = SimpleNamespace(
        receipt_path=str(receipt_path),
        receipt_hash=_HASH_A,
        payload=receipt_payload,
    )
    return policy, execution, read_model, receipt


def _active_row(stock_code: str) -> dict[str, object]:
    return {
        "stock_code": stock_code,
        "status": "active_candidate",
        "calibrated_probability_status": "active_effective",
        "calibrated_probability_bp": 6400,
        "model_version": "candidate-2026-09-14",
        "ranking_score_bp": 7200,
    }


def test_model_choice_receipt_binds_all_saved_candidate_pins(monkeypatch) -> None:
    import ml_module.recommendation_inference_provenance as provenance

    row = _active_row("2330")
    policy, execution, read_model, receipt = _model_receipt_case([row])
    monkeypatch.setattr(
        provenance, "read_inference_projection_receipt", lambda *args, **kwargs: receipt
    )

    evidence = PersonalizationDecisionRecorder.validate_selected_stock_model_evidence(
        read_model=read_model,
        execution=execution,
        stock_code="2330",
        decision_date="2026-09-27",
        policy_snapshot=policy,
        requested_mode="personal_calibrated_probability",
        event_effective_mode="personal_calibrated_probability",
    )

    assert evidence is not None
    assert evidence.candidate_json_sha256 == _HASH_A
    assert evidence.candidate_manifest_hash == _HASH_B
    assert evidence.candidate_artifact_hash == _HASH_C
    assert evidence.candidate_freeze_hash == _HASH_A
    assert evidence.dataset_hash == _HASH_B
    assert evidence.calibrated_probability_bp == 6400


def test_model_choice_matches_nested_rows_from_canonical_frozen_query_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """真實 query.get 凍結巢狀 JSON 後，仍與 immutable receipt 精確比對。"""

    import ml_module.recommendation_inference_provenance as provenance

    row = _active_row("2330")
    row["nested_evidence"] = {
        "warnings": ["one", "two"],
        "details": [{"code": "source", "values": [1, None, 3]}],
    }
    policy, _simple_execution, _simple_read_model, receipt = _model_receipt_case(
        [row]
    )
    receipt_path = Path(receipt.receipt_path).resolve()
    receipt.payload["candidate_identity"]["candidate_root"] = (
        "c:\\isolated\\candidate\\."
    )

    monkeypatch.setattr(
        provenance,
        "read_inference_projection_receipt",
        lambda *args, **kwargs: receipt,
    )

    result_id = str(receipt.payload["result_id"])
    decision_day = date.fromisoformat(str(receipt.payload["decision_date"]))
    binding = MLReceiptBinding(
        receipt_ref=VersionReference(ReferenceKind.ML_RECEIPT, str(receipt_path)),
        receipt_hash=_HASH_A,
        result_id=result_id,
        decision_date=decision_day,
        model_candidate_id="candidate-2026-09-14",
        projected_stock_codes=("2330",),
        cost_scenario_hash=receipt.payload["cost_scenario_hash"],
    )
    execution = RecommendationExecution(
        result_id=result_id,
        request=Request(as_of_date=decision_day),
        context=Context(
            as_of_date=decision_day,
            decision_at=datetime(2026, 9, 27, 12, tzinfo=timezone.utc),
        ),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(
            items=(
                RecommendationItem(
                    stock_code="2330",
                    universe_ref=UniverseReference(
                        snapshot_id="synthetic-universe",
                        as_of_date=decision_day,
                        members_hash="synthetic-members",
                    ),
                ),
            )
        ),
        ml_availability=MLAvailability(status=MLAvailabilityStatus.AVAILABLE),
        ml_projection_refs=(
            VersionReference(
                ReferenceKind.ML_PROJECTION,
                str(receipt.payload["projection_rows_sha256"]),
            ),
        ),
        ml_receipt_refs=(binding,),
    )
    metadata = ArtifactIndexMetadata(
        result_id=result_id,
        payload_hash=_HASH_A,
        artifact_sha256=_HASH_B,
        schema_version=RecommendationExecution.schema_version,
        schema_revision=RecommendationExecution.schema_revision,
        label="synthetic saved recommendation",
        notes=None,
        persisted_at="2026-09-27T12:00:00+00:00",
    )
    record = ArtifactIndexRecord(
        metadata=metadata,
        artifact_name=f"{result_id}.json",
        metadata_present=True,
        metadata_payload_hash=_HASH_A,
    )
    envelope = ExecutionReadEnvelope(
        execution=execution,
        schema_version=RecommendationExecution.schema_version,
        schema_revision=RecommendationExecution.schema_revision,
        payload_hash=_HASH_A,
        raw_payload_sha256=_HASH_B,
        raw_payload=json.dumps({"result_id": result_id}).encode("utf-8"),
    )

    class _Persistence:
        def read_verified_envelope(self, requested_result_id: str):
            assert requested_result_id == result_id
            return record, envelope

    read_model = RecommendationExecutionQueries(_Persistence()).get(result_id)
    assert read_model is not None
    frozen_row = read_model.ml_projection_rows[0]
    assert type(frozen_row["nested_evidence"]["warnings"]) is tuple
    assert type(frozen_row["nested_evidence"]["details"][0]["values"]) is tuple

    evidence = PersonalizationDecisionRecorder.validate_selected_stock_model_evidence(
        read_model=read_model,
        execution=execution,
        stock_code="2330",
        decision_date="2026-09-27",
        policy_snapshot=policy,
        requested_mode="personal_calibrated_probability",
        event_effective_mode="personal_calibrated_probability",
    )

    assert evidence is not None
    assert evidence.calibrated_probability_bp == 6400


def test_personal_model_choice_accepts_only_explicit_saved_rule_fallback(monkeypatch) -> None:
    import ml_module.recommendation_inference_provenance as provenance

    active = _active_row("1101")
    fallback = RecommendationCalibrationProjection.unavailable(
        stock_code="2330", warning="personal_candidate_row_unavailable"
    ).to_dict()
    policy, execution, read_model, receipt = _model_receipt_case([active, fallback])
    monkeypatch.setattr(
        provenance, "read_inference_projection_receipt", lambda *args, **kwargs: receipt
    )

    evidence = PersonalizationDecisionRecorder.validate_selected_stock_model_evidence(
        read_model=read_model,
        execution=execution,
        stock_code="2330",
        decision_date="2026-09-27",
        policy_snapshot=policy,
        requested_mode="personal_calibrated_probability",
        event_effective_mode="personal_calibrated_probability",
    )
    assert evidence is None

    corrupted_fallback = dict(fallback)
    corrupted_fallback["raw_calibrated_probability_bp"] = 5800
    bad_policy, bad_execution, bad_read_model, bad_receipt = _model_receipt_case(
        [active, corrupted_fallback]
    )
    monkeypatch.setattr(
        provenance,
        "read_inference_projection_receipt",
        lambda *args, **kwargs: bad_receipt,
    )
    with pytest.raises(PersonalizationDecisionRecorderError, match="projection/fallback"):
        PersonalizationDecisionRecorder.validate_selected_stock_model_evidence(
            read_model=bad_read_model,
            execution=bad_execution,
            stock_code="2330",
            decision_date="2026-09-27",
            policy_snapshot=bad_policy,
            requested_mode="personal_calibrated_probability",
            event_effective_mode="personal_calibrated_probability",
        )


def test_personal_choice_does_not_downgrade_unverifiable_model_identity(monkeypatch) -> None:
    import ml_module.recommendation_inference_provenance as provenance

    row = _active_row("2330")
    policy, execution, read_model, receipt = _model_receipt_case([row])
    tampered_payload = dict(receipt.payload)
    tampered_payload["candidate_identity"] = {
        **receipt.payload["candidate_identity"],
        "candidate_artifact_hash": _HASH_A,
    }
    bad_receipt = SimpleNamespace(
        receipt_path=receipt.receipt_path,
        receipt_hash=receipt.receipt_hash,
        payload=tampered_payload,
    )
    monkeypatch.setattr(
        provenance,
        "read_inference_projection_receipt",
        lambda *args, **kwargs: bad_receipt,
    )
    with pytest.raises(PersonalizationDecisionRecorderError, match="candidate_artifact_hash"):
        PersonalizationDecisionRecorder.validate_selected_stock_model_evidence(
            read_model=read_model,
            execution=execution,
            stock_code="2330",
            decision_date="2026-09-27",
            policy_snapshot=policy,
            requested_mode="personal_calibrated_probability",
            event_effective_mode="personal_calibrated_probability",
        )

    empty_execution = SimpleNamespace(ml_receipt_refs=(), ml_projection_refs=())
    missing_model = SimpleNamespace(
        result_id="recommendation-20260927-001",
        ml_read_status="unavailable",
        ml_projection_rows=(),
    )
    with pytest.raises(PersonalizationDecisionRecorderError, match="無法核驗"):
        PersonalizationDecisionRecorder.validate_selected_stock_model_evidence(
            read_model=missing_model,
            execution=empty_execution,
            stock_code="2330",
            decision_date="2026-09-27",
            policy_snapshot=policy,
            requested_mode="personal_calibrated_probability",
            event_effective_mode="personal_calibrated_probability",
        )


def test_recorder_uses_same_source_identity_fallback_but_requires_hash() -> None:
    context = SimpleNamespace(
        universe_identity=None,
        universe_snapshot_ref=SimpleNamespace(reference_id="snapshot:input-7"),
        data_snapshot_refs=(),
    )
    assert PersonalizationDecisionRecorder._choice_source_snapshot(context) == (
        "snapshot:input-7",
        "",
    )

    hashed_context = SimpleNamespace(
        universe_identity=SimpleNamespace(
            snapshot=SimpleNamespace(
                universe_snapshot_id="universe-7",
                universe_snapshot_hash=_HASH_C,
            )
        ),
        universe_snapshot_ref=None,
        data_snapshot_refs=(),
    )
    assert PersonalizationDecisionRecorder._choice_source_snapshot(hashed_context) == (
        "universe-7",
        _HASH_C,
    )
    with pytest.raises(ValueError, match="source_snapshot_hash"):
        _choice(source_snapshot_hash="")


def _canonical_rule_only_query_fixture(
    result_id: str = "recommendation-choice-journal-001",
    *,
    include_policy_event: bool = True,
    requested_mode: str = "rule_only",
    projection_rows: list[dict[str, object]] | None = None,
):
    """以真 execution codec 與 query 建立隔離的已保存 canonical fixture。

    若傳入模型 rows，回傳值第二項是由測試 receipt reader 接縫提供的固定
    synthetic receipt；它驗證保存／消費鏈，不代表正式模型自然載入或推論。
    """

    from app_module.recommendation.contracts import (
        ExecutionEvent,
        UniversePolicyIdentity,
        UniverseSnapshotIdentity,
    )

    decision_day = date(2026, 9, 27)
    decision_at = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
    selected_codes = ["1101", "2330"]
    source_provider_id = "isolated-test-provider.v1"
    policy_spec = {
        "schema": "recommendation-universe-policy.v1",
        "selection_algorithm": "test-exact-codes.v1",
        "selection_mode": "explicit",
        "industry_filter": "all",
        "max_stocks": 2,
        "source_provider_id": source_provider_id,
        "requested_codes": selected_codes,
    }
    policy_hash = canonical_payload_hash(policy_spec)
    policy_id = f"recommendation-universe-policy-v1:{policy_hash.removeprefix('sha256:')}"
    selected_codes_hash = canonical_payload_hash({"selected_codes": selected_codes})
    snapshot_spec = {
        "schema": "recommendation-universe-snapshot.v1",
        "universe_policy_id": policy_id,
        "source_provider_id": source_provider_id,
        "decision_date": decision_day.isoformat(),
        "selection_mode": "explicit",
        "selected_codes": selected_codes,
        "selected_count": len(selected_codes),
        "selected_codes_hash": selected_codes_hash,
        "requested_codes": selected_codes,
    }
    snapshot_hash = canonical_payload_hash(snapshot_spec)
    snapshot_id = (
        "recommendation-universe-snapshot-v1:"
        + snapshot_hash.removeprefix("sha256:")
    )
    universe = RecommendationUniverseIdentity(
        universe_id=(
            "recommendation-universe-v1:"
            + snapshot_hash.removeprefix("sha256:")
        ),
        universe_hash=snapshot_hash,
        universe_identity_schema="recommendation-universe-snapshot.v1",
        policy=UniversePolicyIdentity(
            universe_policy_id=policy_id,
            universe_policy_hash=policy_hash,
            universe_policy_schema=str(policy_spec["schema"]),
            universe_policy_spec_json=json.dumps(
                policy_spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        ),
        snapshot=UniverseSnapshotIdentity(
            universe_snapshot_id=snapshot_id,
            universe_snapshot_hash=snapshot_hash,
            universe_snapshot_schema=str(snapshot_spec["schema"]),
            universe_snapshot_source_provider_id=source_provider_id,
            universe_snapshot_selected_codes_hash=selected_codes_hash,
            universe_snapshot_spec_json=json.dumps(
                snapshot_spec,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )
    policy_snapshot = _policy_snapshot(mode=requested_mode)
    receipt = None
    receipt_bindings: tuple[MLReceiptBinding, ...] = ()
    projection_refs: tuple[VersionReference, ...] = ()
    ml_availability = MLAvailability(status=MLAvailabilityStatus.NOT_REQUESTED)
    event_effective_mode = "rule_only"
    if projection_rows is not None:
        if requested_mode != "personal_calibrated_probability":
            raise ValueError("model projection fixture requires personal mode")
        candidate = policy_snapshot["candidate"]
        if not isinstance(candidate, dict):
            raise ValueError("personal fixture policy candidate is missing")
        event_effective_mode = (
            "personal_calibrated_probability"
            if any(row.get("status") == "active_candidate" for row in projection_rows)
            else "rule_only"
        )
        receipt_path = Path(
            f"C:/isolated/personal-choice-receipts/{result_id}.json"
        ).resolve()
        candidate_identity = {
            key: candidate[key]
            for key in (
                "candidate_id",
                "candidate_root",
                "candidate_manifest_hash",
                "candidate_artifact_hash",
                "candidate_freeze_hash",
                "dataset_hash",
            )
        }
        candidate_identity["candidate_json_sha256"] = candidate[
            "candidate_json_sha256"
        ]
        receipt_payload = {
            "result_id": result_id,
            "decision_date": decision_day.isoformat(),
            "candidate_identity": candidate_identity,
            "cost_scenario_hash": _HASH_C,
            "projection_rows_sha256": _HASH_B,
            "projections": projection_rows,
        }
        receipt = SimpleNamespace(
            receipt_path=str(receipt_path),
            receipt_hash=_HASH_A,
            payload=receipt_payload,
        )
        receipt_bindings = (
            MLReceiptBinding(
                receipt_ref=VersionReference(
                    ReferenceKind.ML_RECEIPT, str(receipt_path)
                ),
                receipt_hash=_HASH_A,
                result_id=result_id,
                decision_date=decision_day,
                model_candidate_id=str(candidate["candidate_id"]),
                projected_stock_codes=tuple(
                    str(row["stock_code"]) for row in projection_rows
                ),
                cost_scenario_hash=_HASH_C,
            ),
        )
        projection_refs = (
            VersionReference(ReferenceKind.ML_PROJECTION, _HASH_B),
        )
        ml_availability = MLAvailability(status=MLAvailabilityStatus.AVAILABLE)
    events = (
        (
            ExecutionEvent(
                event_type="personal_use_policy_snapshot",
                message="隔離測試保存的本次個人政策快照。",
                occurred_at=decision_at,
                details={
                    "schema_version": "recommendation-personal-use-policy-snapshot.v1",
                    "result_id": result_id,
                    "decision_at": decision_at.isoformat(timespec="microseconds"),
                    "policy_snapshot": policy_snapshot,
                    "requested_mode": requested_mode,
                    "effective_mode": event_effective_mode,
                },
            ),
        )
        if include_policy_event
        else ()
    )
    execution = RecommendationExecution(
        result_id=result_id,
        request=Request(as_of_date=decision_day),
        context=Context(
            as_of_date=decision_day,
            decision_at=decision_at,
            universe_identity=universe,
        ),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(
            items=tuple(
                RecommendationItem(
                    stock_code=code,
                    rank=index,
                    universe_ref=UniverseReference(
                        snapshot_id=snapshot_id,
                        as_of_date=decision_day,
                        members_hash=selected_codes_hash,
                    ),
                )
                for index, code in enumerate(selected_codes, start=1)
            )
        ),
        ml_availability=ml_availability,
        ml_projection_refs=projection_refs,
        ml_receipt_refs=receipt_bindings,
        events=events,
    )
    raw_payload = encode_execution(execution)
    envelope = decode_execution_envelope(raw_payload)
    metadata = ArtifactIndexMetadata(
        result_id=result_id,
        payload_hash=envelope.payload_hash,
        artifact_sha256=envelope.raw_payload_sha256,
        schema_version=envelope.schema_version,
        schema_revision=envelope.schema_revision,
        label="隔離測試保存推薦",
        notes=None,
        persisted_at="2026-09-27T12:00:00+00:00",
    )
    record = ArtifactIndexRecord(
        metadata=metadata,
        artifact_name=f"{result_id}.json",
        metadata_present=True,
        metadata_payload_hash=envelope.payload_hash,
    )

    class _VerifiedCanonicalPersistence:
        def read_verified_envelope(self, requested_result_id: str):
            if requested_result_id != result_id:
                raise KeyError(requested_result_id)
            return record, envelope

    return RecommendationExecutionQueries(_VerifiedCanonicalPersistence()), receipt


def _choice_read_service(
    tmp_path: Path,
    *,
    journal_path: Path,
    queries: RecommendationExecutionQueries,
) -> PersonalizationReadService:
    return PersonalizationReadService(
        ReadOnlyRecommendationSource(tmp_path / "read-only-output"),
        ReadOnlyJournalRevisionSource(journal_path),
        ReadOnlyEvidenceSource(tmp_path / "read-only-evidence.sqlite"),
        execution_queries=queries,
    )


def test_personal_choice_uses_journal_cas_and_fresh_exact_readback(
    tmp_path: Path,
) -> None:
    """真 Journal/JSONL CAS 與新 recorder/read service 讀回；資料全隔離。"""

    result_id = "recommendation-choice-journal-001"
    stock_code = "2330"
    request_id = "personal-choice-journal-request-001"
    queries, _receipt = _canonical_rule_only_query_fixture(result_id)
    journal_path = tmp_path / "portfolio" / "journal_entries.jsonl"
    journal = JournalService(
        SimpleNamespace(output_root=tmp_path / "unused-output-root"),
        journal_path=journal_path,
    )
    recorder = PersonalizationDecisionRecorder(
        journal,
        canonical_execution_reader=queries.get,
        now=lambda: "2026-09-27T12:01:00.000000+00:00",
    )

    saved = recorder.record_personal_recommendation_choice(
        result_id=result_id,
        stock_code=stock_code,
        choice="adopt",
        request_id=request_id,
        actor="isolated-test-user",
    )
    assert saved.choice.choice == "adopt"
    assert saved.choice.effective_mode == "rule_only"
    assert len(journal.list_decision_revisions()) == 1

    # 模擬重新啟動後的新 service/recorder：相同 request 是冪等讀回，
    # 同一 request 改成不同選擇則拒絕，兩者都不能多寫一筆。
    fresh_journal = JournalService(
        SimpleNamespace(output_root=tmp_path / "unused-output-root"),
        journal_path=journal_path,
    )
    fresh_recorder = PersonalizationDecisionRecorder(
        fresh_journal,
        canonical_execution_reader=queries.get,
        now=lambda: "2026-09-27T12:02:00.000000+00:00",
    )
    retry = fresh_recorder.record_personal_recommendation_choice(
        result_id=result_id,
        stock_code=stock_code,
        choice="adopt",
        request_id=request_id,
        actor="isolated-test-user",
    )
    assert retry == saved
    with pytest.raises(PersonalizationDecisionRecorderError, match="different content"):
        fresh_recorder.record_personal_recommendation_choice(
            result_id=result_id,
            stock_code=stock_code,
            choice="reject",
            request_id=request_id,
            actor="isolated-test-user",
        )
    assert len(fresh_journal.list_decision_revisions()) == 1

    # 使用新的唯讀 PersonalizationReadService，由真 JSONL exact reader 按結果/股票
    # 讀回同一 typed choice，並再次綁定 canonical recommendation 身分。
    read_service = _choice_read_service(
        tmp_path, journal_path=journal_path, queries=queries
    )
    readback_report = read_service.read_personal_recommendation_choices(
        result_id, stock_code
    )
    assert readback_report.source_completeness_status == "verified"
    assert len(readback_report.choices) == 1
    readback_entry = readback_report.choices[0]
    readback = readback_entry.choice
    canonical = read_service.read_canonical_execution_exact(result_id)
    assert canonical is not None and canonical.execution is not None
    assert readback == saved.choice
    assert readback.result_id == canonical.result_id == result_id
    assert readback.stock_code == stock_code
    assert readback.decision_date == canonical.execution.context.as_of_date.isoformat()
    assert readback_entry.revision_id == request_id
    assert readback_entry.continuity_event_id == request_id
    assert readback_entry.outcome_link_status == "not_requested"
    assert readback_report.to_dict()["writes_allowed"] is False
    assert (
        readback.source_snapshot_id
        == canonical.execution.context.universe_identity.snapshot.universe_snapshot_id
    )
    assert (
        readback.source_snapshot_hash
        == canonical.execution.context.universe_identity.snapshot.universe_snapshot_hash
    )


@pytest.mark.parametrize(
    "tamper_field",
    (
        "entity_type",
        "revision_id",
        "continuity_event_id",
        "both_outer_ids",
        "decision_identity",
        "inner_request_id",
        "created_at_mismatch",
        "created_at_missing",
        "linked_target",
    ),
)
def test_personal_choice_retry_rejects_outer_binding_tampering_without_append(
    tmp_path: Path, tamper_field: str
) -> None:
    result_id = f"choice-outer-binding-{tamper_field}"
    stock_code = "2330"
    request_id = f"choice-outer-binding-request-{tamper_field}"
    queries, _receipt = _canonical_rule_only_query_fixture(result_id)
    journal_path = tmp_path / "portfolio" / "journal_entries.jsonl"
    journal = JournalService(
        SimpleNamespace(output_root=tmp_path / "unused-output-root"),
        journal_path=journal_path,
    )
    recorder = PersonalizationDecisionRecorder(
        journal,
        canonical_execution_reader=queries.get,
        now=lambda: "2026-09-27T12:01:00.000000+00:00",
    )
    recorder.record_personal_recommendation_choice(
        result_id=result_id,
        stock_code=stock_code,
        choice="adopt",
        request_id=request_id,
        actor="isolated-test-user",
    )

    raw_record = json.loads(journal_path.read_text(encoding="utf-8"))
    raw_payload = raw_record["payload"]
    typed_choice = raw_payload["personal_recommendation_choice"]
    if tamper_field == "entity_type":
        raw_record["entity_type"] = "decision"
    elif tamper_field == "revision_id":
        raw_record["revision_id"] = request_id + "-changed"
    elif tamper_field == "continuity_event_id":
        raw_record["continuity_event_id"] = request_id + "-changed"
    elif tamper_field == "both_outer_ids":
        raw_record["revision_id"] = request_id + "-changed"
        raw_record["continuity_event_id"] = request_id + "-changed"
    elif tamper_field == "decision_identity":
        raw_record["decision_identity"]["result_id"] = result_id + "-changed"
        raw_record["result_id"] = result_id + "-changed"
    elif tamper_field == "inner_request_id":
        typed_choice["request_id"] = request_id + "-changed"
        typed_choice["choice_hash"] = canonical_payload_hash(
            {key: value for key, value in typed_choice.items() if key != "choice_hash"}
        )
    elif tamper_field == "created_at_mismatch":
        raw_record["created_at"] = "2026-09-27T12:00:59.000000+00:00"
    elif tamper_field == "created_at_missing":
        raw_record.pop("created_at")
    elif tamper_field == "linked_target":
        raw_record["linked_id"] = result_id + "-changed"
        raw_payload["linked_id"] = result_id + "-changed"
    else:  # pragma: no cover - keeps the parameter table exhaustive
        raise AssertionError(tamper_field)
    tampered_bytes = (
        json.dumps(raw_record, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    journal_path.write_bytes(tampered_bytes)

    with pytest.raises(PersonalizationDecisionRecorderError):
        recorder.record_personal_recommendation_choice(
            result_id=result_id,
            stock_code=stock_code,
            choice="adopt",
            request_id=request_id,
            actor="isolated-test-user",
        )
    assert journal_path.read_bytes() == tampered_bytes


def test_personal_choice_retry_rejects_duplicate_inner_request_without_append(
    tmp_path: Path,
) -> None:
    result_id = "choice-duplicate-request-result"
    stock_code = "2330"
    request_id = "choice-duplicate-request"
    queries, _receipt = _canonical_rule_only_query_fixture(result_id)
    journal_path = tmp_path / "portfolio" / "journal_entries.jsonl"
    journal = JournalService(
        SimpleNamespace(output_root=tmp_path / "unused-output-root"),
        journal_path=journal_path,
    )
    recorder = PersonalizationDecisionRecorder(
        journal,
        canonical_execution_reader=queries.get,
        now=lambda: "2026-09-27T12:01:00.000000+00:00",
    )
    recorder.record_personal_recommendation_choice(
        result_id=result_id,
        stock_code=stock_code,
        choice="adopt",
        request_id=request_id,
    )

    raw_record = json.loads(journal_path.read_text(encoding="utf-8"))
    duplicate = json.loads(json.dumps(raw_record))
    duplicate["revision_id"] = request_id + "-duplicate"
    duplicate["continuity_event_id"] = request_id + "-duplicate"
    tampered_bytes = journal_path.read_bytes() + (
        json.dumps(duplicate, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    journal_path.write_bytes(tampered_bytes)

    with pytest.raises(PersonalizationDecisionRecorderError, match="duplicated"):
        recorder.record_personal_recommendation_choice(
            result_id=result_id,
            stock_code=stock_code,
            choice="adopt",
            request_id=request_id,
        )
    assert journal_path.read_bytes() == tampered_bytes


def test_personal_choice_readback_requires_outer_created_at(
    tmp_path: Path,
) -> None:
    result_id = "choice-readback-created-at-result"
    stock_code = "2330"
    request_id = "choice-readback-created-at-request"
    queries, _receipt = _canonical_rule_only_query_fixture(result_id)
    journal_path = tmp_path / "portfolio" / "journal_entries.jsonl"
    journal = JournalService(
        SimpleNamespace(output_root=tmp_path / "unused-output-root"),
        journal_path=journal_path,
    )
    recorder = PersonalizationDecisionRecorder(
        journal,
        canonical_execution_reader=queries.get,
        now=lambda: "2026-09-27T12:01:00.000000+00:00",
    )
    recorder.record_personal_recommendation_choice(
        result_id=result_id,
        stock_code=stock_code,
        choice="adopt",
        request_id=request_id,
    )
    raw_record = json.loads(journal_path.read_text(encoding="utf-8"))
    raw_record.pop("created_at")
    journal_path.write_text(
        json.dumps(raw_record, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    report = _choice_read_service(
        tmp_path, journal_path=journal_path, queries=queries
    ).read_personal_recommendation_choices(result_id, stock_code)

    assert report.source_completeness_status == "incomplete"
    assert report.choices == ()
    assert any(
        item.startswith("personal_choice_row_invalid:")
        for item in report.diagnostics
    )


def test_personal_choice_readback_fails_closed_on_journal_identity_conflict(
    tmp_path: Path,
) -> None:
    result_id = "recommendation-choice-readback-conflict-001"
    stock_code = "2330"
    queries, _receipt = _canonical_rule_only_query_fixture(result_id)
    journal_path = tmp_path / "portfolio" / "journal_entries.jsonl"
    journal = JournalService(
        SimpleNamespace(output_root=tmp_path / "unused-output-root"),
        journal_path=journal_path,
    )
    recorder = PersonalizationDecisionRecorder(
        journal,
        canonical_execution_reader=queries.get,
        now=lambda: "2026-09-27T12:01:00.000000+00:00",
    )
    recorder.record_personal_recommendation_choice(
        result_id=result_id,
        stock_code=stock_code,
        choice="adopt",
        request_id="choice-readback-conflict-request",
    )

    raw = json.loads(journal_path.read_text(encoding="utf-8"))
    raw["decision_identity"]["source_snapshot_hash"] = _HASH_A
    journal_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
    read_service = _choice_read_service(
        tmp_path, journal_path=journal_path, queries=queries
    )

    report = read_service.read_personal_recommendation_choices(result_id, stock_code)

    assert report.source_completeness_status == "incomplete"
    assert report.choices == ()
    assert any(item.startswith("personal_choice_row_invalid:") for item in report.diagnostics)


def test_personal_choice_refuses_legacy_execution_without_saved_policy_event(
    tmp_path: Path,
) -> None:
    result_id = "recommendation-choice-legacy-without-policy"
    queries, _receipt = _canonical_rule_only_query_fixture(
        result_id, include_policy_event=False
    )
    journal_path = tmp_path / "portfolio" / "journal_entries.jsonl"
    journal = JournalService(
        SimpleNamespace(output_root=tmp_path / "unused-output-root"),
        journal_path=journal_path,
    )
    recorder = PersonalizationDecisionRecorder(
        journal,
        canonical_execution_reader=queries.get,
        now=lambda: "2026-09-27T12:01:00.000000+00:00",
    )

    with pytest.raises(PersonalizationDecisionRecorderError, match="先以個人模式重新產生"):
        recorder.record_personal_recommendation_choice(
            result_id=result_id,
            stock_code="2330",
            choice="adopt",
            request_id="legacy-no-policy-request",
        )
    assert journal.list_decision_revisions() == []
    assert not journal_path.exists()


def test_personal_choice_journal_writer_binds_selected_active_model_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ml_module.recommendation_inference_provenance as provenance

    result_id = "recommendation-choice-active-model-001"
    rows = [_active_row("1101"), _active_row("2330")]
    queries, receipt = _canonical_rule_only_query_fixture(
        result_id,
        requested_mode="personal_calibrated_probability",
        projection_rows=rows,
    )
    assert receipt is not None
    monkeypatch.setattr(
        provenance, "read_inference_projection_receipt", lambda *args, **kwargs: receipt
    )
    journal = JournalService(
        SimpleNamespace(output_root=tmp_path / "unused-output-root"),
        journal_path=tmp_path / "portfolio" / "journal_entries.jsonl",
    )
    recorder = PersonalizationDecisionRecorder(
        journal,
        canonical_execution_reader=queries.get,
        now=lambda: "2026-09-27T12:01:00.000000+00:00",
    )

    saved = recorder.record_personal_recommendation_choice(
        result_id=result_id,
        stock_code="2330",
        choice="adopt",
        request_id="active-model-choice-request",
    )

    assert saved.choice.effective_mode == "personal_calibrated_probability"
    assert saved.choice.model_evidence is not None
    assert saved.choice.model_evidence.candidate_artifact_hash == _HASH_C
    assert saved.choice.model_evidence.receipt_hash == _HASH_A
    revisions = journal.list_decision_revisions()
    assert len(revisions) == 1
    assert revisions[0].payload["personal_recommendation_choice"] == saved.choice.to_dict()
    report = _choice_read_service(
        tmp_path, journal_path=journal.store.journal_file, queries=queries
    ).read_personal_recommendation_choices(result_id, "2330")
    assert report.source_completeness_status == "verified"
    assert len(report.choices) == 1
    assert report.choices[0].choice == saved.choice
    assert report.choices[0].choice.effective_mode == "personal_calibrated_probability"


def test_personal_choice_journal_writer_keeps_explicit_per_stock_fallback_rule_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ml_module.recommendation_inference_provenance as provenance

    result_id = "recommendation-choice-model-fallback-001"
    active = _active_row("1101")
    fallback = RecommendationCalibrationProjection.unavailable(
        stock_code="2330", warning="personal_candidate_row_unavailable"
    ).to_dict()
    queries, receipt = _canonical_rule_only_query_fixture(
        result_id,
        requested_mode="personal_calibrated_probability",
        projection_rows=[active, fallback],
    )
    assert receipt is not None
    monkeypatch.setattr(
        provenance, "read_inference_projection_receipt", lambda *args, **kwargs: receipt
    )
    journal = JournalService(
        SimpleNamespace(output_root=tmp_path / "unused-output-root"),
        journal_path=tmp_path / "portfolio" / "journal_entries.jsonl",
    )
    recorder = PersonalizationDecisionRecorder(
        journal,
        canonical_execution_reader=queries.get,
        now=lambda: "2026-09-27T12:01:00.000000+00:00",
    )

    saved = recorder.record_personal_recommendation_choice(
        result_id=result_id,
        stock_code="2330",
        choice="reject",
        request_id="fallback-choice-request",
    )

    assert saved.choice.requested_mode == "personal_calibrated_probability"
    assert saved.choice.effective_mode == "rule_only"
    assert saved.choice.model_evidence is None
    assert len(journal.list_decision_revisions()) == 1
    report = _choice_read_service(
        tmp_path, journal_path=journal.store.journal_file, queries=queries
    ).read_personal_recommendation_choices(result_id, "2330")
    assert report.source_completeness_status == "verified"
    assert len(report.choices) == 1
    assert report.choices[0].choice == saved.choice
    assert report.choices[0].choice.effective_mode == "rule_only"


@pytest.mark.parametrize(
    "tamper_field",
    ("calibrated_probability_bp", "candidate_artifact_hash", "receipt_hash"),
)
def test_personal_choice_readback_rejects_rehashed_model_evidence_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper_field: str,
) -> None:
    """重新計算 typed choice hash 仍不能替換已保存 receipt 的逐股票證據。"""

    import ml_module.recommendation_inference_provenance as provenance

    result_id = f"recommendation-choice-readback-tamper-{tamper_field}"
    queries, receipt = _canonical_rule_only_query_fixture(
        result_id,
        requested_mode="personal_calibrated_probability",
        projection_rows=[_active_row("1101"), _active_row("2330")],
    )
    assert receipt is not None
    monkeypatch.setattr(
        provenance, "read_inference_projection_receipt", lambda *args, **kwargs: receipt
    )
    journal_path = tmp_path / "portfolio" / "journal_entries.jsonl"
    journal = JournalService(
        SimpleNamespace(output_root=tmp_path / "unused-output-root"),
        journal_path=journal_path,
    )
    recorder = PersonalizationDecisionRecorder(
        journal,
        canonical_execution_reader=queries.get,
        now=lambda: "2026-09-27T12:01:00.000000+00:00",
    )
    recorder.record_personal_recommendation_choice(
        result_id=result_id,
        stock_code="2330",
        choice="adopt",
        request_id=f"tamper-{tamper_field}-request",
    )

    rows = journal_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    raw_row = json.loads(rows[0])
    payload = raw_row["payload"]["personal_recommendation_choice"]
    model_evidence = payload["model_evidence"]
    if tamper_field == "calibrated_probability_bp":
        model_evidence[tamper_field] = 6401
    elif tamper_field == "candidate_artifact_hash":
        model_evidence[tamper_field] = _HASH_A
    else:
        model_evidence[tamper_field] = _HASH_B
    unhashed_choice = {
        key: value for key, value in payload.items() if key != "choice_hash"
    }
    payload["choice_hash"] = canonical_payload_hash(unhashed_choice)
    journal_path.write_text(
        json.dumps(raw_row, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    report = _choice_read_service(
        tmp_path, journal_path=journal_path, queries=queries
    ).read_personal_recommendation_choices(result_id, "2330")

    assert report.source_completeness_status == "incomplete"
    assert report.choices == ()
    assert any(
        item.startswith("personal_choice_row_invalid:")
        for item in report.diagnostics
    )


def test_personal_choice_journal_writer_rejects_corrupt_model_fallback_without_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ml_module.recommendation_inference_provenance as provenance

    result_id = "recommendation-choice-corrupt-fallback-001"
    active = _active_row("1101")
    fallback = RecommendationCalibrationProjection.unavailable(
        stock_code="2330", warning="personal_candidate_row_unavailable"
    ).to_dict()
    fallback["raw_calibrated_probability_bp"] = 5800
    queries, receipt = _canonical_rule_only_query_fixture(
        result_id,
        requested_mode="personal_calibrated_probability",
        projection_rows=[active, fallback],
    )
    assert receipt is not None
    monkeypatch.setattr(
        provenance, "read_inference_projection_receipt", lambda *args, **kwargs: receipt
    )
    journal_path = tmp_path / "portfolio" / "journal_entries.jsonl"
    journal = JournalService(
        SimpleNamespace(output_root=tmp_path / "unused-output-root"),
        journal_path=journal_path,
    )
    recorder = PersonalizationDecisionRecorder(
        journal,
        canonical_execution_reader=queries.get,
        now=lambda: "2026-09-27T12:01:00.000000+00:00",
    )

    with pytest.raises(PersonalizationDecisionRecorderError, match="projection/fallback"):
        recorder.record_personal_recommendation_choice(
            result_id=result_id,
            stock_code="2330",
            choice="adopt",
            request_id="corrupt-fallback-choice-request",
        )
    assert journal.list_decision_revisions() == []
    assert not journal_path.exists()
