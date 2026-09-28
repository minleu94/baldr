from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import multiprocessing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app_module.recommendation.personal_use_policy import (
    PERSONAL_CALIBRATED_PROBABILITY_MODE,
    RULE_ONLY_MODE,
    PersonalCalibrationCandidateV1,
    PersonalSourceFileIdentityV1,
    PersonalSourceReplayScopeV1,
    PersonalSourceTimeBindingProposalV1,
    PersonalUsePolicyConflict,
    PersonalUsePolicyError,
    RecommendationPersonalUsePolicyV1,
    RecommendationPersonalUsePolicyV2,
    RecommendationPersonalUseSelectionV1,
    RecommendationPersonalUseSelectionV2,
    load_personal_use_policy,
    load_personal_use_policy_snapshot,
    rollback_personal_use_policy,
    rollback_personal_use_policy_v2,
    save_personal_use_policy,
    save_personal_use_policy_v2,
    list_personal_use_policy_revisions,
    validate_personal_use_policy_snapshot,
)
from app_module.recommendation_calibration_consumer import (
    RecommendationCalibrationConsumer,
)
from app_module.recommendation_service import RecommendationService
from app_module.recommendation.contracts import (
    Context,
    ExecutionEvent,
    ExecutionStatus,
    RecommendationExecution,
    Request,
)
from app_module.personalization_contract import (
    PersonalRecommendationChoice,
    canonical_payload_hash,
    read_personal_use_policy_snapshot_event,
)
from app_module.recommendation.codec import decode_execution, encode_execution
from app_module.recommendation.execute import _capture_events
from app_module.recommendation.ml_postcalibration_handoff import (
    RecommendationPostCalibrationHandoffV1,
)
from recommendation_test_support import build_recommendation_test_service
from data_module.company_registry import (
    COMPANY_REGISTRY_SOURCE_CONTRACT_ATTR,
    COMPANY_REGISTRY_SOURCE_CONTRACT_SCHEMA_VERSION,
)


def _save_from_child(path_text: str, result_queue: multiprocessing.Queue) -> None:
    try:
        save_personal_use_policy(
            path_text,
            RecommendationPersonalUseSelectionV1(
                scope_id="cas-race", mode=RULE_ONLY_MODE
            ),
            expected_revision=0,
        )
    except PersonalUsePolicyConflict:
        result_queue.put("conflict")
    except BaseException as exc:  # pragma: no cover - reported to parent
        result_queue.put(f"error:{type(exc).__name__}:{exc}")
    else:
        result_queue.put("saved")


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _candidate(tmp_path: Path) -> PersonalCalibrationCandidateV1:
    candidate_root = tmp_path / "candidate"
    candidate_root.mkdir()
    marker = "sha256:" + ("a" * 64)
    payload = {
        "candidate_id": "personal-candidate-1",
        "manifest_hash": marker,
        "artifact_hash": marker,
        "candidate_freeze_hash": marker,
        "dataset_hash": marker,
        "training_as_of": "2026-09-01",
        "fixed_round_trip_cost_bp": 50,
    }
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (candidate_root / "candidate.json").write_bytes(raw)
    return PersonalCalibrationCandidateV1(
        candidate_id=payload["candidate_id"],
        candidate_root=str(candidate_root.resolve()),
        candidate_json_sha256=_sha256(raw),
        candidate_manifest_hash=marker,
        candidate_artifact_hash=marker,
        candidate_freeze_hash=marker,
        dataset_hash=marker,
    )


def _source_time_binding(
    tmp_path: Path,
    *,
    candidate: PersonalCalibrationCandidateV1 | None = None,
    database_size: int = 1024,
    source_slice_sha256: str | None = None,
) -> PersonalSourceTimeBindingProposalV1:
    pinned_candidate = candidate or _candidate(tmp_path)
    return PersonalSourceTimeBindingProposalV1(
        source_database_path=str((tmp_path / "source.sqlite").resolve()),
        file_identity=PersonalSourceFileIdentityV1(device=1, inode=22),
        source_database_size_bytes=database_size,
        source_slice_sha256=source_slice_sha256 or _sha256(b"bounded-source-slice"),
        candidate=pinned_candidate,
        replay_scope=PersonalSourceReplayScopeV1(
            dataset_ids=("recommendation-dataset-0123456789abcdef",),
            decision_dates=("2026-09-24",),
            symbols=("2330",),
            sample_count=1,
        ),
    )


def _service(tmp_path: Path) -> RecommendationService:
    config = SimpleNamespace(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        db_file=tmp_path / "source.db",
        default_start_date="2020-01-01",
    )
    provider = MagicMock()
    return build_recommendation_test_service(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=provider,
        regime_detector=MagicMock(),
    )


def test_cold_start_policy_is_explicit_rule_only_without_writing(tmp_path: Path) -> None:
    path = tmp_path / "personal.json"
    policy = RecommendationPersonalUsePolicyV1.default_rule_only("desktop-user")

    assert policy.revision == 0
    assert policy.mode == RULE_ONLY_MODE
    assert policy.confirmed_at is None
    assert policy.storage_path is None
    assert policy.storage_bytes is None
    assert policy.applicable_at("2026-09-27T12:00:00Z")
    assert not path.exists()


def test_pure_snapshot_validator_accepts_cold_persisted_and_pinned_rule_snapshots(
    tmp_path: Path,
) -> None:
    cold = RecommendationPersonalUsePolicyV1.default_rule_only("desktop-user")
    assert validate_personal_use_policy_snapshot(cold.to_dict()) == cold.to_dict()

    path = tmp_path / "personal.json"
    persisted = save_personal_use_policy(
        path,
        RecommendationPersonalUseSelectionV1(
            scope_id="desktop-user", mode=RULE_ONLY_MODE
        ),
        expected_revision=0,
    )
    assert validate_personal_use_policy_snapshot(persisted.to_dict()) == persisted.to_dict()

    pinned_rule = save_personal_use_policy(
        path,
        RecommendationPersonalUseSelectionV1(
            scope_id="desktop-user",
            mode=RULE_ONLY_MODE,
            candidate=_candidate(tmp_path),
        ),
        expected_revision=1,
    )
    assert pinned_rule.candidate is not None
    assert validate_personal_use_policy_snapshot(pinned_rule.to_dict()) == pinned_rule.to_dict()


def test_pure_snapshot_validator_rejects_noncanonical_utc_and_mutable_json_values(
    tmp_path: Path,
) -> None:
    policy = save_personal_use_policy(
        tmp_path / "personal.json",
        RecommendationPersonalUseSelectionV1(
            scope_id="desktop-user", mode=RULE_ONLY_MODE
        ),
        expected_revision=0,
    )
    payload = policy.to_dict()
    payload["confirmed_at"] = str(payload["confirmed_at"]).replace("Z", "+00:00")
    body = {key: value for key, value in payload.items() if key != "policy_sha256"}
    payload["policy_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    with pytest.raises(PersonalUsePolicyError):
        validate_personal_use_policy_snapshot(payload)

    malformed = policy.to_dict()
    malformed["extra"] = object()
    with pytest.raises(PersonalUsePolicyError):
        validate_personal_use_policy_snapshot(malformed)


def test_save_load_clock_binding_and_revisioned_rollback(tmp_path: Path) -> None:
    path = tmp_path / "personal.json"
    first_selection = RecommendationPersonalUseSelectionV1(
        scope_id="desktop-user", mode=RULE_ONLY_MODE
    )
    before = datetime.now(timezone.utc)
    first = save_personal_use_policy(path, first_selection, expected_revision=0)
    after = datetime.now(timezone.utc)

    assert before <= datetime.fromisoformat(first.confirmed_at.replace("Z", "+00:00")) <= after
    assert first.revision == 1
    assert first.applicable_at(after + timedelta(seconds=1))
    assert not first.applicable_at(before - timedelta(seconds=1))
    loaded = load_personal_use_policy(path)
    assert loaded.to_dict() == first.to_dict()
    assert loaded.storage_bytes == path.read_bytes()

    second = save_personal_use_policy(
        path,
        RecommendationPersonalUseSelectionV1(
            scope_id="desktop-user", mode=RULE_ONLY_MODE
        ),
        expected_revision=1,
    )
    rolled_back = rollback_personal_use_policy(
        path,
        target_revision=first.revision,
        target_policy_sha256=first.policy_sha256,
        expected_revision=second.revision,
    )
    assert rolled_back.revision == 3
    assert rolled_back.scope_id == first.scope_id
    assert rolled_back.mode == first.mode
    assert rolled_back.rollback_of_revision == first.revision
    assert rolled_back.rollback_of_policy_sha256 == first.policy_sha256
    assert load_personal_use_policy(path).to_dict() == rolled_back.to_dict()


def test_rollback_rejects_revision_bytes_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "personal.json"
    first = save_personal_use_policy(
        path,
        RecommendationPersonalUseSelectionV1(scope_id="user", mode=RULE_ONLY_MODE),
        expected_revision=0,
    )
    second = save_personal_use_policy(
        path,
        RecommendationPersonalUseSelectionV1(scope_id="user", mode=RULE_ONLY_MODE),
        expected_revision=1,
    )
    archive_dir = path.with_name(path.name + ".revisions")
    wrong_archive = archive_dir / f"rev-00000001-{second.policy_sha256[7:]}.json"
    wrong_archive.write_bytes(second.storage_bytes)

    with pytest.raises(PersonalUsePolicyError, match="hash 不符"):
        rollback_personal_use_policy(
            path,
            target_revision=1,
            target_policy_sha256=second.policy_sha256,
            expected_revision=2,
        )
    assert load_personal_use_policy(path).revision == 2
    assert first.revision == 1


def test_two_processes_with_same_expected_revision_have_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "personal.json"
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    processes = [
        context.Process(target=_save_from_child, args=(str(path), result_queue))
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
    try:
        assert all(process.exitcode == 0 for process in processes)
        outcomes = sorted(result_queue.get(timeout=3) for _ in processes)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(2)
        result_queue.close()

    assert outcomes == ["conflict", "saved"]
    assert load_personal_use_policy(path).revision == 1


def test_personal_invocation_keeps_policy_bytes_when_next_revision_is_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app_module.recommendation_calibration_consumer as consumer_module

    candidate = _candidate(tmp_path)
    path = tmp_path / "personal.json"
    original = save_personal_use_policy(
        path,
        RecommendationPersonalUseSelectionV1(
            scope_id="desktop-user",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            candidate=candidate,
        ),
        expected_revision=0,
    )
    base_service = _service(tmp_path)
    original_invocation = base_service.with_personal_use_policy(original)
    original_consumer = original_invocation.calibration_consumer
    assert type(original_consumer) is RecommendationCalibrationConsumer
    assert original_consumer._personal_use_policy_bytes == original.storage_bytes

    updated = save_personal_use_policy(
        path,
        RecommendationPersonalUseSelectionV1(
            scope_id="desktop-user", mode=RULE_ONLY_MODE
        ),
        expected_revision=1,
    )
    monkeypatch.setattr(
        consumer_module,
        "_current_model_graph_runtime_profile",
        lambda: next(iter(consumer_module._SUPPORTED_MODEL_GRAPH_RUNTIME_PROFILES)),
    )

    no_model = original_consumer.resolve_invocation_no_model_projection_capability_v1(
        invocation_scope_id="personal-snapshot-check",
        decision_date="2026-09-27",
        expected_identity={},
    )
    assert no_model is not None
    resolved = no_model._resolved_consumer_for_isolation()
    assert resolved._personal_use_policy is not None
    assert resolved._personal_use_policy.policy_sha256 == original.policy_sha256
    assert resolved._personal_use_policy_bytes == original.storage_bytes
    assert updated.policy_sha256 != original.policy_sha256

    next_invocation = base_service.with_personal_use_policy(updated)
    assert next_invocation._personal_use_policy is not None
    assert next_invocation._personal_use_policy.revision == updated.revision
    assert next_invocation.calibration_consumer is None
    assert next_invocation.last_run_context is not base_service.last_run_context
    assert next_invocation.last_calibration_projections is not base_service.last_calibration_projections


def test_personal_candidate_identity_requires_valid_pinned_hashes(tmp_path: Path) -> None:
    with pytest.raises(PersonalUsePolicyError, match="candidate_json_sha256"):
        PersonalCalibrationCandidateV1(
            candidate_id="candidate",
            candidate_root=str(tmp_path.resolve()),
            candidate_json_sha256="not-a-hash",
            candidate_manifest_hash="sha256:" + "a" * 64,
            candidate_artifact_hash="sha256:" + "b" * 64,
            candidate_freeze_hash="sha256:" + "c" * 64,
            dataset_hash="sha256:" + "d" * 64,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        ("policy_version", 99),
        ("revision", True),
        ("confirmed_at", "2026-09-27T00:00:00"),
        ("rollback_of_revision", 1),
        ("policy_sha256", "sha256:" + "0" * 64),
    ),
)
def test_consumer_rejects_forged_policy_snapshot_fields(
    tmp_path: Path, mutation: tuple[str, object]
) -> None:
    path = tmp_path / "personal.json"
    policy = save_personal_use_policy(
        path,
        RecommendationPersonalUseSelectionV1(scope_id="desktop-user", mode=RULE_ONLY_MODE),
        expected_revision=0,
    )
    name, value = mutation
    payload = policy.to_dict()
    payload[name] = value
    if name != "policy_sha256":
        body = {key: item for key, item in payload.items() if key != "policy_sha256"}
        payload["policy_sha256"] = "sha256:" + hashlib.sha256(
            json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    forged = replace(
        policy,
        revision=payload.get("revision", policy.revision),
        confirmed_at=payload.get("confirmed_at", policy.confirmed_at),
        policy_sha256=payload["policy_sha256"],
        storage_bytes=raw,
        rollback_of_revision=payload.get("rollback_of_revision"),
        rollback_of_policy_sha256=payload.get("rollback_of_policy_sha256"),
    )

    with pytest.raises(PersonalUsePolicyError):
        RecommendationCalibrationConsumer(
            pointer_path=path,
            feature_schema=(),
            feature_registry_hash="sha256:" + "1" * 64,
            data_root=tmp_path / "data",
            personal_use_policy=forged,
        )


def test_policy_snapshot_is_saved_as_event_and_legacy_execution_has_none(
    tmp_path: Path,
) -> None:
    policy = save_personal_use_policy(
        tmp_path / "personal.json",
        RecommendationPersonalUseSelectionV1(scope_id="desktop-user", mode=RULE_ONLY_MODE),
        expected_revision=0,
    )
    service = _service(tmp_path).with_personal_use_policy(policy)
    decision_at = (
        datetime.fromisoformat(policy.confirmed_at.replace("Z", "+00:00"))
        + timedelta(seconds=1)
    ).isoformat(timespec="microseconds")
    service.last_run_context = {
        "result_id": "personal-result-1",
        "decision_at": decision_at,
    }
    service._apply_recommendation_calibration(
        [], decision_date="2026-09-27"
    )

    def _events(context: dict[str, object]):
        state = {"last_run_context": context}
        snapshot = SimpleNamespace(materialize=lambda: state)
        return _capture_events(
            snapshot,
            {},
            RecommendationPostCalibrationHandoffV1(
                consumer_configured=False, attempted=False
            ),
            status=ExecutionStatus.CANCELLED,
            body_result=None,
            result_id=str(context.get("result_id") or ""),
            context_as_of_date=(
                date.fromisoformat(str(context["as_of_date"]))
                if context.get("as_of_date")
                else None
            ),
            context_decision_at=datetime.fromisoformat(
                str(context["decision_at"]).replace("Z", "+00:00")
            ),
        )

    events = _events(service.last_run_context)
    policy_event = next(
        event for event in events if event.event_type == "personal_use_policy_snapshot"
    )
    assert set(policy_event.details) == {
        "schema_version",
        "result_id",
        "decision_at",
        "policy_snapshot",
        "requested_mode",
        "effective_mode",
    }
    assert policy_event.details["schema_version"] == "recommendation-personal-use-policy-snapshot.v1"
    assert policy_event.details["policy_snapshot"] == policy.to_dict()
    assert policy_event.details["requested_mode"] == RULE_ONLY_MODE
    assert policy_event.details["effective_mode"] == RULE_ONLY_MODE
    assert policy_event.occurred_at == datetime.fromisoformat(decision_at)

    execution = RecommendationExecution(
        result_id="personal-result-1",
        request=Request(),
        context=Context(),
        status=ExecutionStatus.CANCELLED,
        events=events,
        failure_reason="cancelled",
    )
    restored = decode_execution(encode_execution(execution))
    restored_event = next(
        event for event in restored.events if event.event_type == "personal_use_policy_snapshot"
    )
    assert restored_event.details == policy_event.details

    old_events = _events({"result_id": "old-result", "decision_at": decision_at})
    assert all(event.event_type != "personal_use_policy_snapshot" for event in old_events)


@pytest.mark.parametrize(
    "failure",
    (
        "future_confirmation",
        "invalid_mode",
        "result_id_mismatch",
        "decision_clock_mismatch",
    ),
)
def test_personal_policy_event_rejects_unbound_mode_or_future_confirmation(
    tmp_path: Path,
    failure: str,
) -> None:
    policy = save_personal_use_policy(
        tmp_path / "personal.json",
        RecommendationPersonalUseSelectionV1(
            scope_id="desktop-user", mode=RULE_ONLY_MODE
        ),
        expected_revision=0,
    )
    confirmed = datetime.fromisoformat(policy.confirmed_at.replace("Z", "+00:00"))
    decision_at = (
        confirmed - timedelta(seconds=1)
        if failure == "future_confirmation"
        else confirmed + timedelta(seconds=1)
    ).isoformat(timespec="microseconds")
    context = {
        "result_id": (
            "other-result" if failure == "result_id_mismatch" else "policy-event-negative"
        ),
        "decision_at": decision_at,
        "personal_use_policy": policy.to_dict(),
        "personal_use_requested_mode": (
            "unsupported" if failure == "invalid_mode" else RULE_ONLY_MODE
        ),
        "personal_use_effective_mode": RULE_ONLY_MODE,
    }
    legacy_snapshot = SimpleNamespace(
        materialize=lambda: {"last_run_context": context}
    )
    with pytest.raises(ValueError, match="personal policy event"):
        _capture_events(
            legacy_snapshot,
            {},
            RecommendationPostCalibrationHandoffV1(
                consumer_configured=False, attempted=False
            ),
            status=ExecutionStatus.CANCELLED,
            body_result=None,
            result_id="policy-event-negative",
            context_as_of_date=None,
            context_decision_at=datetime.fromisoformat(
                decision_at.replace("Z", "+00:00")
            )
            + (
                timedelta(seconds=1)
                if failure == "decision_clock_mismatch"
                else timedelta()
            ),
        )


def test_v2_policy_cas_dispatches_across_schemas_and_rule_only_clears_trust(
    tmp_path: Path,
) -> None:
    path = tmp_path / "personal-v2.json"
    first_v1 = save_personal_use_policy(
        path,
        RecommendationPersonalUseSelectionV1(scope_id="desktop-user", mode=RULE_ONLY_MODE),
        expected_revision=0,
    )
    candidate = _candidate(tmp_path)
    binding = _source_time_binding(tmp_path, candidate=candidate)
    second_v2 = save_personal_use_policy_v2(
        path,
        RecommendationPersonalUseSelectionV2(
            scope_id="desktop-user",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            source_time_binding=binding,
        ),
        expected_revision=first_v1.revision,
    )

    assert type(second_v2) is RecommendationPersonalUsePolicyV2
    assert second_v2.revision == 2
    assert second_v2.candidate == candidate
    assert second_v2.source_time_trust is not None
    assert second_v2.source_time_trust.confirmed_at == second_v2.confirmed_at
    assert second_v2.source_time_trust.research_only is True
    assert second_v2.source_time_trust.official_historical_pit_verified is False
    assert second_v2.validate_snapshot().storage_bytes == second_v2.storage_bytes
    assert validate_personal_use_policy_snapshot(second_v2.to_dict()) == second_v2.to_dict()
    assert type(load_personal_use_policy_snapshot(path)) is RecommendationPersonalUsePolicyV2
    with pytest.raises(PersonalUsePolicyError):
        load_personal_use_policy(path)

    third_v1 = save_personal_use_policy(
        path,
        RecommendationPersonalUseSelectionV1(scope_id="desktop-user", mode=RULE_ONLY_MODE),
        expected_revision=second_v2.revision,
    )
    assert third_v1.revision == 3
    assert third_v1.candidate is None
    history = list_personal_use_policy_revisions(path)
    assert [policy.revision for policy in history] == [1, 2]
    assert type(history[0]) is RecommendationPersonalUsePolicyV1
    assert type(history[1]) is RecommendationPersonalUsePolicyV2
    assert history[1].candidate == candidate


def test_v2_rule_only_rejects_source_binding_before_changing_saved_bytes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "personal-v2-rule-only.json"
    candidate = _candidate(tmp_path)
    saved = save_personal_use_policy_v2(
        path,
        RecommendationPersonalUseSelectionV2(
            scope_id="desktop-user",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            source_time_binding=_source_time_binding(tmp_path, candidate=candidate),
        ),
        expected_revision=0,
    )
    before = path.read_bytes()

    with pytest.raises(PersonalUsePolicyError, match="rule_only"):
        RecommendationPersonalUseSelectionV2(
            scope_id="desktop-user",
            mode=RULE_ONLY_MODE,
            source_time_binding=_source_time_binding(tmp_path, candidate=candidate),
        )

    assert path.read_bytes() == before
    assert load_personal_use_policy_snapshot(path).revision == saved.revision

    rule_path = tmp_path / "personal-v2-cold-rule.json"
    rule_policy = save_personal_use_policy_v2(
        rule_path,
        RecommendationPersonalUseSelectionV2(
            scope_id="desktop-user", mode=RULE_ONLY_MODE
        ),
        expected_revision=0,
    )
    invocation = _service(tmp_path).with_personal_use_policy(rule_policy)
    assert type(invocation._personal_use_policy) is RecommendationPersonalUsePolicyV2
    assert invocation._personal_use_policy.source_time_trust is None
    assert invocation.calibration_consumer is None


def test_v2_policy_rejects_inconsistent_trust_after_outer_hash_is_recomputed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "personal-v2-tamper.json"
    saved = save_personal_use_policy_v2(
        path,
        RecommendationPersonalUseSelectionV2(
            scope_id="desktop-user",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            source_time_binding=_source_time_binding(tmp_path),
        ),
        expected_revision=0,
    )
    tampered = json.loads(saved.storage_bytes.decode("utf-8"))
    tampered["source_time_trust"]["candidate"]["candidate_id"] = "different-candidate"
    body = {key: value for key, value in tampered.items() if key != "policy_sha256"}
    tampered["policy_sha256"] = _sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )

    with pytest.raises(PersonalUsePolicyError, match="hash|source_time_trust"):
        validate_personal_use_policy_snapshot(tampered)


def test_v2_rollback_requires_fresh_matching_binding_and_new_confirmation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "personal-v2-rollback.json"
    original_binding = _source_time_binding(tmp_path, database_size=1024)
    first = save_personal_use_policy_v2(
        path,
        RecommendationPersonalUseSelectionV2(
            scope_id="desktop-user",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            source_time_binding=original_binding,
        ),
        expected_revision=0,
    )
    rule_only = save_personal_use_policy_v2(
        path,
        RecommendationPersonalUseSelectionV2(scope_id="desktop-user", mode=RULE_ONLY_MODE),
        expected_revision=1,
    )
    before = path.read_bytes()
    with pytest.raises(PersonalUsePolicyError, match="重新確認"):
        rollback_personal_use_policy_v2(
            path,
            target_revision=1,
            target_policy_sha256=first.policy_sha256,
            expected_revision=rule_only.revision,
        )
    assert path.read_bytes() == before

    fresh_same_slice_larger_file = _source_time_binding(
        tmp_path,
        candidate=original_binding.candidate,
        database_size=2048,
    )
    rolled_back = rollback_personal_use_policy_v2(
        path,
        target_revision=1,
        target_policy_sha256=first.policy_sha256,
        expected_revision=rule_only.revision,
        source_time_binding=fresh_same_slice_larger_file,
    )
    assert rolled_back.revision == 3
    assert rolled_back.rollback_of_revision == 1
    assert rolled_back.rollback_of_policy_sha256 == first.policy_sha256
    assert rolled_back.confirmed_at != first.confirmed_at
    assert rolled_back.source_time_trust is not None
    assert rolled_back.source_time_trust.source_database_size_bytes == 2048

    current_bytes = path.read_bytes()
    changed_slice = replace(
        fresh_same_slice_larger_file,
        source_slice_sha256=_sha256(b"changed-slice"),
    )
    with pytest.raises(PersonalUsePolicyError, match="相同來源切片"):
        rollback_personal_use_policy_v2(
            path,
            target_revision=1,
            target_policy_sha256=first.policy_sha256,
            expected_revision=rolled_back.revision,
            source_time_binding=changed_slice,
        )
    assert path.read_bytes() == current_bytes


def test_v2_event_and_choice_readback_bind_source_trust_without_changing_v1_wire(
    tmp_path: Path,
) -> None:
    path = tmp_path / "personal-v2-event.json"
    policy = save_personal_use_policy_v2(
        path,
        RecommendationPersonalUseSelectionV2(
            scope_id="desktop-user",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            source_time_binding=_source_time_binding(tmp_path),
        ),
        expected_revision=0,
    )
    assert policy.source_time_trust is not None
    confirmed = datetime.fromisoformat(policy.confirmed_at.replace("Z", "+00:00"))
    decision_at = confirmed + timedelta(seconds=1)
    decision_text = decision_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
    result_id = "personal-v2-result"
    legacy_context = {
        "result_id": result_id,
        "decision_at": decision_text,
        "personal_use_policy": policy.to_dict(),
        "personal_use_requested_mode": PERSONAL_CALIBRATED_PROBABILITY_MODE,
        "personal_use_effective_mode": RULE_ONLY_MODE,
    }
    events = _capture_events(
        SimpleNamespace(materialize=lambda: {"last_run_context": legacy_context}),
        {},
        RecommendationPostCalibrationHandoffV1(
            consumer_configured=False, attempted=False
        ),
        status=ExecutionStatus.CANCELLED,
        body_result=None,
        result_id=result_id,
        context_as_of_date=date(2026, 9, 27),
        context_decision_at=decision_at,
    )
    policy_event = next(
        event for event in events if event.event_type == "personal_use_policy_snapshot"
    )
    assert policy_event.details["schema_version"] == (
        "recommendation-personal-use-policy-snapshot.v2"
    )
    assert policy_event.details["source_time_basis"] == "user_declared_source_time"
    assert policy_event.details["research_only"] is True
    assert policy_event.details["official_historical_pit_verified"] is False
    execution = RecommendationExecution(
        result_id=result_id,
        request=Request(),
        context=Context(as_of_date=date(2026, 9, 27), decision_at=decision_at),
        status=ExecutionStatus.CANCELLED,
        events=events,
        failure_reason="cancelled",
    )
    decoded_event = read_personal_use_policy_snapshot_event(
        execution, expected_result_id=result_id
    )
    assert decoded_event["policy_snapshot"] == policy.to_dict()
    assert decoded_event["source_time_basis"] == "user_declared_source_time"

    choice = PersonalRecommendationChoice(
        result_id=result_id,
        stock_code="2330",
        decision_date="2026-09-27",
        source_snapshot_id="universe-v2-1",
        source_snapshot_hash=_sha256(b"universe"),
        canonical_payload_hash=_sha256(b"payload"),
        raw_artifact_sha256=_sha256(b"artifact"),
        choice="adopt",
        requested_mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
        effective_mode=RULE_ONLY_MODE,
        action_at=decision_text,
        recorded_at=decision_text,
        request_id="choice-v2-1",
        policy_snapshot=decoded_event["policy_snapshot"],
    )
    assert canonical_payload_hash(choice.policy_snapshot) == canonical_payload_hash(
        decoded_event["policy_snapshot"]
    )

    bad_details = dict(policy_event.details)
    bad_snapshot = dict(bad_details["policy_snapshot"])
    bad_trust = dict(bad_snapshot["source_time_trust"])
    bad_trust["source_slice_sha256"] = _sha256(b"forged source")
    bad_snapshot["source_time_trust"] = bad_trust
    bad_details["policy_snapshot"] = bad_snapshot
    bad_event = replace(policy_event, details=bad_details)
    bad_execution = replace(
        execution,
        events=tuple(bad_event if event is policy_event else event for event in events),
    )
    with pytest.raises(ValueError, match="policy event|policy snapshot|policy_sha256"):
        read_personal_use_policy_snapshot_event(
            bad_execution, expected_result_id=result_id
        )


def test_current_mapper_source_snapshot_is_detached_hashed_and_saved_as_event(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    source_contract = {
        "schema_version": COMPANY_REGISTRY_SOURCE_CONTRACT_SCHEMA_VERSION,
        "status": "captured",
        "scope": "current_classification_only",
        "pit_eligible": False,
        "generated_at": "2026-09-27T10:00:00.000000Z",
        "artifact": {"name": "companies.csv", "bytes": 10, "sha256": "sha256:" + "a" * 64},
        "sources": [],
        "warnings": [],
        "source_contract_sha256": "",
    }
    source_contract["source_contract_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(
            {
                key: value
                for key, value in source_contract.items()
                if key != "source_contract_sha256"
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    companies_frame = SimpleNamespace(
        attrs={COMPANY_REGISTRY_SOURCE_CONTRACT_ATTR: source_contract}
    )
    service.industry_mapper = SimpleNamespace(companies_df=companies_frame)
    service.last_run_context = {
        "result_id": "current-mapper-result",
        "as_of_date": "2026-09-24",
        "decision_at": "2026-09-27T18:00:00.000000Z",
    }
    service._record_current_industry_mapping_use("current_filter_selection")
    source_contract["warnings"].append("mutated-after-capture")
    service._record_current_industry_mapping_use(
        "current_industry_index_performance_for_reason"
    )
    service._finalize_current_industry_mapping_snapshot()

    state = {"last_run_context": service.last_run_context}
    events = _capture_events(
        SimpleNamespace(materialize=lambda: state),
        {},
        RecommendationPostCalibrationHandoffV1(
            consumer_configured=False, attempted=False
        ),
        status=ExecutionStatus.CANCELLED,
        body_result=None,
        result_id="current-mapper-result",
        context_as_of_date=date(2026, 9, 24),
        context_decision_at=datetime.fromisoformat("2026-09-27T18:00:00+00:00"),
    )
    source_event = next(
        event
        for event in events
        if event.event_type == "company_registry_source_snapshot"
    )
    snapshot = source_event.details["snapshot"]
    assert snapshot["schema_version"] == "recommendation-company-registry-source-snapshot.v1"
    assert snapshot["result_id"] == "current-mapper-result"
    assert snapshot["decision_at"] == service.last_run_context["decision_at"]
    assert snapshot["data_as_of_date"] == "2026-09-24"
    assert snapshot["scope"] == "current_classification_only"
    assert snapshot["pit_eligible"] is False
    assert snapshot["company_registry_source_status"] == "captured"
    assert snapshot["industry_index_source_status"] == "unknown"
    assert snapshot["usage"] == (
        "current_filter_selection",
        "current_industry_index_performance_for_reason",
    )
    assert snapshot["company_registry_source_contract"]["warnings"] == ()
    assert "industry_index_source_contract_unavailable_for_current_use" in snapshot[
        "warnings"
    ]
    assert snapshot["snapshot_sha256"].startswith("sha256:")

    tampered_context = json.loads(json.dumps(service.last_run_context))
    tampered_snapshot = tampered_context["industry_mapping_source_snapshot"]
    tampered_snapshot["company_registry_source_contract"]["artifact"]["bytes"] += 1
    tampered_snapshot.pop("snapshot_sha256", None)
    tampered_snapshot["snapshot_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(
            tampered_snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValueError, match="industry mapping source snapshot binding"):
        _capture_events(
            SimpleNamespace(
                materialize=lambda: {"last_run_context": tampered_context}
            ),
            {},
            RecommendationPostCalibrationHandoffV1(
                consumer_configured=False, attempted=False
            ),
            status=ExecutionStatus.CANCELLED,
            body_result=None,
            result_id="current-mapper-result",
            context_as_of_date=date(2026, 9, 24),
            context_decision_at=datetime.fromisoformat(
                "2026-09-27T18:00:00+00:00"
            ),
        )


def test_missing_current_mapper_source_contract_stays_unknown(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    service.industry_mapper = SimpleNamespace(companies_df=SimpleNamespace(attrs={}))
    service.last_run_context = {
        "result_id": "unknown-current-mapper-result",
        "as_of_date": "2026-09-24",
        "decision_at": "2026-09-27T18:00:00.000000Z",
    }
    service._record_current_industry_mapping_use(
        "current_industry_context_display_reason"
    )
    service._finalize_current_industry_mapping_snapshot()
    snapshot = service.last_run_context["industry_mapping_source_snapshot"]
    assert snapshot["company_registry_source_status"] == "unknown"
    assert snapshot["company_registry_source_contract"] is None
    assert "company_registry_source_contract_missing" in snapshot["warnings"]


def test_current_mapper_event_preserves_missing_decision_clock_as_unknown(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    service.industry_mapper = SimpleNamespace(companies_df=SimpleNamespace(attrs={}))
    service.last_run_context = {
        "result_id": "clockless-current-mapper-result",
        "as_of_date": "2026-09-24",
    }
    service._record_current_industry_mapping_use(
        "current_industry_context_display_reason"
    )
    service._finalize_current_industry_mapping_snapshot()
    snapshot = service.last_run_context["industry_mapping_source_snapshot"]
    assert snapshot["decision_at"] is None
    assert (
        "recommendation_decision_clock_unavailable_for_current_mapper_use"
        in snapshot["warnings"]
    )

    events = _capture_events(
        SimpleNamespace(
            materialize=lambda: {"last_run_context": service.last_run_context}
        ),
        {},
        RecommendationPostCalibrationHandoffV1(
            consumer_configured=False, attempted=False
        ),
        status=ExecutionStatus.CANCELLED,
        body_result=None,
        result_id="clockless-current-mapper-result",
        context_as_of_date=date(2026, 9, 24),
        context_decision_at=None,
    )
    source_event = next(
        event
        for event in events
        if event.event_type == "company_registry_source_snapshot"
    )
    assert source_event.occurred_at is None
    assert source_event.details["snapshot"]["decision_at"] is None


def test_tampered_current_mapper_contract_hash_is_captured_as_unknown(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    source_contract = {
        "schema_version": COMPANY_REGISTRY_SOURCE_CONTRACT_SCHEMA_VERSION,
        "status": "captured",
        "scope": "current_classification_only",
        "pit_eligible": False,
        "generated_at": "2026-09-27T10:00:00.000000Z",
        "artifact": {"name": "companies.csv", "bytes": 10, "sha256": "sha256:" + "a" * 64},
        "sources": [],
        "warnings": [],
        "source_contract_sha256": "sha256:" + "b" * 64,
    }
    service.industry_mapper = SimpleNamespace(
        companies_df=SimpleNamespace(
            attrs={COMPANY_REGISTRY_SOURCE_CONTRACT_ATTR: source_contract}
        )
    )
    service.last_run_context = {
        "result_id": "tampered-current-mapper-result",
        "as_of_date": "2026-09-24",
        "decision_at": "2026-09-27T18:00:00.000000Z",
    }
    service._record_current_industry_mapping_use(
        "current_industry_context_display_reason"
    )
    service._finalize_current_industry_mapping_snapshot()

    snapshot = service.last_run_context["industry_mapping_source_snapshot"]
    assert snapshot["company_registry_source_status"] == "unknown"
    assert "company_registry_source_contract_hash_mismatch" in snapshot["warnings"]


def test_synthetic_lineage_candidate_stays_rule_only_without_promotion(
    tmp_path: Path,
) -> None:
    from test_recommendation_service_calibration_integration import (
        _core_feature_samples,
        _make_database,
        _recommendation,
        _verified_candidate,
    )
    from decision_module.recommendation.contracts import RecommendationItem
    from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY

    registry = CORE_LONG_HISTORY_FEATURE_REGISTRY
    trained_result, candidate_root, candidate_metadata = _verified_candidate(
        tmp_path,
        candidate_day="2026-06-01",
        training_as_of="2026-05-31",
        samples=_core_feature_samples(),
        feature_names=registry.canonical_ids,
        feature_schema=registry.canonical_schema,
        feature_registry_hash=registry.registry_hash,
        dataset_id="personal-use-lineage-only",
    )
    candidate_path = candidate_root / "candidate.json"
    candidate_raw = candidate_path.read_bytes()
    candidate = PersonalCalibrationCandidateV1(
        candidate_id=trained_result.candidate_id,
        candidate_root=str(candidate_root.resolve()),
        candidate_json_sha256=_sha256(candidate_raw),
        candidate_manifest_hash=str(candidate_metadata["manifest_hash"]),
        candidate_artifact_hash=str(candidate_metadata["artifact_hash"]),
        candidate_freeze_hash=str(candidate_metadata["candidate_freeze_hash"]),
        dataset_hash=str(candidate_metadata["dataset_hash"]),
    )
    policy = save_personal_use_policy(
        tmp_path / "personal.json",
        RecommendationPersonalUseSelectionV1(
            scope_id="personal-synthetic-fixture",
            mode=PERSONAL_CALIBRATED_PROBABILITY_MODE,
            candidate=candidate,
        ),
        expected_revision=0,
    )

    data_root = tmp_path / "formal-data-readonly"
    output_root = tmp_path / "output"
    database = tmp_path / "source.db"
    first_day = date(2026, 1, 1)
    cutoff_day = date(2026, 9, 24)
    _make_database(
        database,
        days=(cutoff_day - first_day).days + 1,
        start=first_day,
    )
    config = SimpleNamespace(
        db_file=database,
        default_start_date=first_day.isoformat(),
        output_root=output_root,
        data_root=data_root,
    )
    base_consumer = RecommendationCalibrationConsumer(
        pointer_path=tmp_path / "global-pointer-must-not-be-used.json",
        feature_schema=registry.canonical_schema,
        feature_registry_hash=registry.registry_hash,
        data_root=data_root,
    )
    service = build_recommendation_test_service(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=MagicMock(),
        regime_detector=MagicMock(),
        calibration_consumer=base_consumer,
    ).with_personal_use_policy(policy)

    def run_personal_inference(result_id: str):
        # 這是直接呼叫 service adapter 的合成隔離測試時鐘，不是 producer receipt。
        decision_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        service.last_run_context = {
            "result_id": result_id,
            "decision_at": decision_at,
            "as_of_date": cutoff_day.isoformat(),
            "warnings": [],
        }
        service._personalization_execution_clocks = {
            "decision_at": decision_at,
            "available_at": decision_at,
        }
        recommendation = _recommendation()
        service._apply_recommendation_calibration(
            [recommendation],
            selected_items=(
                RecommendationItem(
                    stock_code="AAA",
                    stock_name="測試股票",
                    rule_score=Decimal("80"),
                    score_percentile_bp=5_000,
                ),
            ),
            decision_date=cutoff_day.isoformat(),
        )
        return recommendation

    # 合成 fixture 雖有 lineage 檔案，仍沒有可驗證的真實來源證據；
    # 不得僅憑 lineage 將它提升為個人可用模型。
    assert Path(str(candidate_metadata["training_lineage_manifest_path"])).is_file()
    assert not (tmp_path / "authority").exists()
    result = run_personal_inference("personal-synthetic-lineage-only")
    assert result.calibration_status in {"rule_only", "unavailable"}
    assert result.calibrated_probability_bp is None
    assert service.last_run_context["personal_use_requested_mode"] == (
        PERSONAL_CALIBRATED_PROBABILITY_MODE
    )
    assert service.last_run_context["personal_use_effective_mode"] == RULE_ONLY_MODE
    projection = service.last_calibration_projections.get("AAA")
    assert projection is None or projection.status != "active_candidate"
    assert not (data_root / "recommendation_learning" / "inference_projection").exists()
    assert not (tmp_path / "authority").exists()
    assert not (tmp_path / "global-pointer-must-not-be-used.json").exists()
