"""C1 U5a typed verified-read consumer readiness fixtures。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from app_module.forward_position_thesis_candidate_producer import (
    ForwardPositionThesisCandidateProducer,
    _sha256_json,
)
from app_module.recommendation.contracts import (
    Context,
    ExecutionStatus,
    IndexStatus,
    MLAvailability,
    MLAvailabilityStatus,
    MLReceiptBinding,
    RecommendationConfigSnapshot,
    RecommendationExecution,
    RecommendationResultConfigSnapshot,
    RecommendationRunEvidenceIdentity,
    RecommendationUniverseIdentity,
    ReferenceKind,
    Request,
    SaveReceipt,
    SnapshotCohort,
    SnapshotCohortCoverageStatus,
    StrategyConfigIdentity,
    UniversePolicyIdentity,
    UniverseSnapshotIdentity,
    VersionReference,
)
from app_module.recommendation.persistence import (
    ExecutionArtifactWriteError,
    RecommendationExecutionPersistence,
)
from app_module.recommendation.queries import (
    RecommendationExecutionQueries,
    RecommendationExecutionReadModel,
)
from app_module.recommendation.save import RecommendationSaveService
from data_module.result_artifact_store import ResultArtifactStore
from decision_module.recommendation.contracts import DecisionBatch, RecommendationItem


_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "c1_consumer_readiness"
_UTC = timezone.utc


def _fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    payload = json.loads((_FIXTURE_ROOT / "r014_saved_execution.json").read_text(encoding="utf-8"))
    manifest = json.loads((_FIXTURE_ROOT / "r014_fixture_manifest.json").read_text(encoding="utf-8"))
    entry = manifest["entries"][0]
    raw = (_FIXTURE_ROOT / entry["file"]).read_bytes()
    assert len(raw) == entry["byte_length"]
    assert "sha256:" + hashlib.sha256(raw).hexdigest() == entry["sha256"]
    return payload, entry


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _reference(kind: ReferenceKind, value: str) -> VersionReference:
    return VersionReference(kind=kind, reference_id=value, version="synthetic-v1")


def _execution(
    fixture: dict[str, Any],
    *,
    include_ml_binding: bool = False,
) -> RecommendationExecution:
    request_raw = fixture["request"]["raw_config_json"]
    request_snapshot = RecommendationConfigSnapshot(
        raw_config_json=request_raw,
        raw_json_sha256=fixture["request"]["raw_json_sha256"],
    )
    cohort_raw = fixture["context"]["snapshot_cohort"]
    cohort = SnapshotCohort(
        cohort_hash=cohort_raw["cohort_hash"],
        requested_symbols=tuple(cohort_raw["requested_symbols"]),
        eligible_symbols=tuple(cohort_raw["eligible_symbols"]),
        missing_symbols=tuple(cohort_raw["missing_symbols"]),
        degraded_symbols=tuple(cohort_raw["degraded_symbols"]),
        excluded_symbols=tuple(cohort_raw["excluded_symbols"]),
        requested_count=cohort_raw["requested_count"],
        eligible_count=cohort_raw["eligible_count"],
        missing_count=cohort_raw["missing_count"],
        degraded_count=cohort_raw["degraded_count"],
        excluded_count=cohort_raw["excluded_count"],
        coverage_status=SnapshotCohortCoverageStatus(cohort_raw["coverage_status"]),
        coverage_by_symbol={},
        eligible_definition=cohort_raw["eligible_definition"],
        missing_definition=cohort_raw["missing_definition"],
        degraded_definition=cohort_raw["degraded_definition"],
        excluded_definition=cohort_raw["excluded_definition"],
        schema_version=cohort_raw["schema_version"],
    )

    strategy_raw = fixture["context"]["strategy_identity"]
    strategy = StrategyConfigIdentity(
        strategy_version_id=strategy_raw["strategy_version_id"],
        strategy_config_id=strategy_raw["strategy_config_id"],
        strategy_config_hash=strategy_raw["strategy_config_hash"],
        strategy_config_schema=strategy_raw["strategy_config_schema"],
        strategy_config_spec_json=_json_text(strategy_raw["strategy_config_spec"]),
    )
    universe_raw = fixture["context"]["universe_identity"]
    policy_raw = universe_raw["policy"]
    policy = UniversePolicyIdentity(
        universe_policy_id=policy_raw["universe_policy_id"],
        universe_policy_hash=policy_raw["universe_policy_hash"],
        universe_policy_schema=policy_raw["universe_policy_schema"],
        universe_policy_spec_json=_json_text(policy_raw["universe_policy_spec"]),
    )
    snapshot_raw = universe_raw["snapshot"]
    snapshot = UniverseSnapshotIdentity(
        universe_snapshot_id=snapshot_raw["universe_snapshot_id"],
        universe_snapshot_hash=snapshot_raw["universe_snapshot_hash"],
        universe_snapshot_schema=snapshot_raw["universe_snapshot_schema"],
        universe_snapshot_source_provider_id=snapshot_raw[
            "universe_snapshot_source_provider_id"
        ],
        universe_snapshot_selected_codes_hash=snapshot_raw[
            "universe_snapshot_selected_codes_hash"
        ],
        universe_snapshot_spec_json=_json_text(snapshot_raw["universe_snapshot_spec"]),
    )
    universe = RecommendationUniverseIdentity(
        universe_id=universe_raw["universe_id"],
        universe_hash=universe_raw["universe_hash"],
        universe_identity_schema=universe_raw["universe_identity_schema"],
        policy=policy,
        snapshot=snapshot,
    )
    evidence = RecommendationRunEvidenceIdentity(
        **fixture["context"]["evidence_identity"]
    )
    result_config = fixture["context"]["result_config"]
    result_snapshot = RecommendationResultConfigSnapshot(
        raw_result_config_json=_json_text(result_config),
        config_sha256=fixture["context"]["config_sha256"],
    )

    request = Request(
        as_of_date=date.fromisoformat(fixture["request"]["as_of_date"]),
        config_ref=_reference(ReferenceKind.CONFIG, "synthetic-r014-config"),
        profile_ref=_reference(ReferenceKind.PROFILE, "synthetic-r014-profile"),
        strategy_ref=_reference(ReferenceKind.STRATEGY, strategy.strategy_config_id or "strategy"),
        universe_policy_ref=_reference(
            ReferenceKind.UNIVERSE_POLICY, policy.universe_policy_id or "universe-policy"
        ),
        config_snapshot=request_snapshot,
        max_stocks=fixture["request"]["max_stocks"],
        top_n=fixture["request"]["top_n"],
    )
    context = Context(
        as_of_date=date.fromisoformat(fixture["context"]["as_of_date"]),
        created_at=datetime.fromisoformat(fixture["context"]["created_at"]),
        available_at=datetime.fromisoformat(fixture["context"]["available_at"]),
        decision_at=datetime.fromisoformat(fixture["context"]["decision_at"]),
        config_ref=request.config_ref,
        profile_ref=request.profile_ref,
        strategy_ref=request.strategy_ref,
        universe_policy_ref=request.universe_policy_ref,
        strategy_identity=strategy,
        universe_identity=universe,
        evidence_identity=evidence,
        snapshot_cohort=cohort,
        result_config_snapshot=result_snapshot,
    )
    items = tuple(
        RecommendationItem(
            stock_code=row["stock_code"],
            stock_name=row["stock_name"],
            rank=row["rank"],
            rule_score=Decimal(row["rule_score"]),
            close_price=Decimal(row["close_price"]),
            price_change=Decimal(row["price_change"]),
            indicator_score=Decimal(row["indicator_score"]),
            pattern_score=Decimal(row["pattern_score"]),
            volume_score=Decimal(row["volume_score"]),
            industry=row["industry"],
            reason_text=row["reason_text"],
            reasons=tuple(row["reasons"]),
            threshold_mode=row["threshold_mode"],
            regime_match=row["regime_match"],
        )
        for row in fixture["recommendations"]
    )
    ml_kwargs: dict[str, Any] = {}
    if include_ml_binding:
        projected_codes = tuple(item.stock_code for item in items)
        ml_kwargs = {
            "ml_availability": MLAvailability(status=MLAvailabilityStatus.AVAILABLE),
            "ml_projection_refs": (
                _reference(ReferenceKind.ML_PROJECTION, "sha256:" + "c" * 64),
            ),
            "ml_receipt_refs": (
                MLReceiptBinding(
                    receipt_ref=_reference(
                        ReferenceKind.ML_RECEIPT,
                        str(_FIXTURE_ROOT / "missing-r014-receipt.json"),
                    ),
                    receipt_hash="sha256:" + "a" * 64,
                    result_id=fixture["result_id"],
                    decision_date=request.as_of_date,
                    model_candidate_id="synthetic-candidate-v1",
                    projected_stock_codes=projected_codes,
                    cost_scenario_hash=None,
                ),
            ),
        }
    return RecommendationExecution(
        result_id=fixture["result_id"],
        request=request,
        context=context,
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=items, regime="SyntheticRegime"),
        **ml_kwargs,
    )


def _stack(tmp_path: Path) -> tuple[
    ResultArtifactStore,
    RecommendationExecutionPersistence,
    RecommendationSaveService,
    RecommendationExecutionQueries,
]:
    runs = tmp_path / "output" / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs / "execution_artifacts",
        database_path=runs / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)
    return store, persistence, RecommendationSaveService(persistence), RecommendationExecutionQueries(persistence)


def _producer(tmp_path: Path) -> ForwardPositionThesisCandidateProducer:
    return ForwardPositionThesisCandidateProducer(
        tmp_path / "forward-candidates",
        now_provider=lambda: datetime(2026, 9, 23, 12, tzinfo=_UTC),
    )


def _save_query_forward(
    execution: RecommendationExecution,
    *,
    store: ResultArtifactStore,
    save: RecommendationSaveService,
    queries: RecommendationExecutionQueries,
    producer: ForwardPositionThesisCandidateProducer,
) -> tuple[SaveReceipt, RecommendationExecutionReadModel, dict[str, Any]]:
    receipt = save.save_execution(execution)
    if receipt.index_status is not IndexStatus.INDEXED:
        raise RuntimeError("synthetic forward caller requires INDEXED save receipt")
    read_model = queries.get(execution.result_id)
    if read_model is None:
        raise RuntimeError("saved execution missing from U4 query readback")
    artifact_path = store.artifact_root / str(receipt.artifact_location)
    return (
        receipt,
        read_model,
        producer.produce_verified_read(
            read_model, receipt, source_artifact_path=artifact_path
        ),
    )


def _blocked(result: dict[str, Any], blocker: str) -> None:
    assert result["status"] == "blocked"
    assert any(blocker in item for item in result["blockers"])


def test_c1_saved_rev2_query_readback_projects_rows_and_independent_hashes(
    tmp_path: Path,
) -> None:
    fixture, manifest_entry = _fixture()
    execution = _execution(fixture)
    assert execution.decision is not None
    # reasons 與 reason_text 是不同 sealed 欄位；forward packet 沿用 U3 reason_text owner。
    object.__setattr__(execution.decision.items[0], "reasons", ("非展示用結構標籤",))
    store, _persistence, save, queries = _stack(tmp_path)
    producer = _producer(tmp_path)

    receipt, read_model, produced = _save_query_forward(
        execution,
        store=store,
        save=save,
        queries=queries,
        producer=producer,
    )

    artifact_path = store.artifact_root / str(receipt.artifact_location)
    raw = artifact_path.read_bytes()
    raw_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
    canonical_content_hash = _sha256_json(json.loads(raw.decode("utf-8")))
    assert receipt.index_status is IndexStatus.INDEXED
    assert read_model.schema_revision == 2
    assert read_model.result_id == execution.result_id == receipt.result_id
    assert produced["status"] == "degraded"
    assert [row["candidate_id"] for row in produced["candidates"]] == [
        f"candidate:{execution.result_id}:AAA",
        f"candidate:{execution.result_id}:BET",
    ]
    assert produced["recommendation_source"]["file_sha256"] == raw_hash
    assert produced["recommendation_source"]["content_sha256"] == canonical_content_hash
    assert produced["recommendation_source"]["payload_hash"] == receipt.payload_hash
    assert produced["recommendation_source"]["config_sha256"] == fixture["expected_hashes"][
        "result_config_sha256"
    ]
    assert produced["recommendation_source"]["request_raw_config_sha256"] == fixture[
        "expected_hashes"
    ]["request_raw_config_sha256"]
    assert produced["recommendation_source"]["strategy_config_hash"] == fixture[
        "expected_hashes"
    ]["strategy_config_hash"]
    assert produced["recommendation_source"]["request_as_of_date"] == "2026-09-21"
    assert produced["decision_date"] == "2026-09-22"
    assert manifest_entry["request_as_of_date"] != manifest_entry["result_decision_date"]

    packets = [json.loads(Path(row["path"]).read_text(encoding="utf-8")) for row in produced["candidates"]]
    assert [packet["instrument"]["stock_code"] for packet in packets] == ["AAA", "BET"]
    assert [packet["decision_observation"]["rank"] for packet in packets] == [1, 2]
    assert packets[0]["decision_observation"]["scores"]["total_score"] == "82.1000"
    assert packets[1]["decision_observation"]["scores"]["total_score"] == "71"
    assert packets[0]["decision_observation"]["recommendation_reasons"] == "AAA 封存推薦理由"
    source_trace = packets[0]["thesis"]["source_trace"]
    assert f"recommendation_payload_hash:{receipt.payload_hash}" in source_trace
    assert f"recommendation_artifact_file_sha256:{raw_hash}" in source_trace
    assert (
        "recommendation_result_config_sha256:"
        + fixture["expected_hashes"]["result_config_sha256"]
    ) in source_trace
    assert artifact_path.read_bytes() == raw


def test_c1_save_failure_never_calls_verified_forward_consumer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, _ = _fixture()
    execution = _execution(fixture)
    store, _persistence, save, queries = _stack(tmp_path)
    producer = _producer(tmp_path)
    producer_call = Mock(wraps=producer.produce_verified_read)
    monkeypatch.setattr(producer, "produce_verified_read", producer_call)

    def fail_save(*_args: object, **_kwargs: object) -> SaveReceipt:
        raise ExecutionArtifactWriteError("synthetic create-only save failure")

    monkeypatch.setattr(save, "save_execution", fail_save)
    with pytest.raises(ExecutionArtifactWriteError):
        _save_query_forward(
            execution,
            store=store,
            save=save,
            queries=queries,
            producer=producer,
        )
    producer_call.assert_not_called()
    assert not store.artifact_root.exists()


@pytest.mark.parametrize(
    ("receipt_change", "read_change", "path_change", "expected"),
    [
        ("pending", None, None, "not_indexed"),
        ("wrong_result", None, None, "result_id_mismatch"),
        ("wrong_payload_hash", None, None, "payload_hash_mismatch"),
        ("wrong_location", None, None, "artifact_location_mismatch"),
        (None, "wrong_raw_hash", None, "raw_hash_mismatch"),
        (None, "legacy", None, "not_canonical_execution"),
        (None, None, "outside_layout", "path_layout_invalid"),
        (None, None, "directory", "not_regular_file"),
        (None, None, "malformed", "recommendation_source_blocked"),
    ],
)
def test_c1_verified_read_rejects_unverified_receipt_read_model_or_path(
    tmp_path: Path,
    receipt_change: str | None,
    read_change: str | None,
    path_change: str | None,
    expected: str,
) -> None:
    fixture, _ = _fixture()
    execution = _execution(fixture)
    store, _persistence, save, queries = _stack(tmp_path)
    producer = _producer(tmp_path)
    receipt = save.save_execution(execution)
    read_model = queries.get(execution.result_id)
    assert read_model is not None
    source = store.artifact_root / str(receipt.artifact_location)
    canonical_source = source
    before = source.read_bytes()

    if receipt_change == "pending":
        receipt = replace(receipt, index_status=IndexStatus.PENDING)
    elif receipt_change == "wrong_result":
        receipt = replace(receipt, result_id="another-result-id")
    elif receipt_change == "wrong_payload_hash":
        receipt = replace(receipt, payload_hash="sha256:" + "0" * 64)
    elif receipt_change == "wrong_location":
        receipt = replace(receipt, artifact_location="different.json")
    if read_change == "wrong_raw_hash":
        read_model = replace(read_model, raw_artifact_sha256="sha256:" + "0" * 64)
    elif read_change == "legacy":
        read_model = replace(
            read_model,
            execution=None,
            legacy_result=object(),
            schema_version=None,
            schema_revision=None,
            payload_hash=None,
        )
    if path_change == "outside_layout":
        outside = tmp_path / "copied-artifact.json"
        outside.write_bytes(before)
        source = outside
    elif path_change == "directory":
        source = store.artifact_root
    elif path_change == "malformed":
        source = None  # type: ignore[assignment]

    rejected = producer.produce_verified_read(
        read_model, receipt, source_artifact_path=source
    )
    _blocked(rejected, expected)
    assert canonical_source.read_bytes() == before


def test_c1_verified_read_rejects_rev1_and_legacy_read_views(tmp_path: Path) -> None:
    fixture_root = _FIXTURE_ROOT
    rev1_path = fixture_root / "r016_execution_rev1.json"
    envelope = json.loads(rev1_path.read_text(encoding="utf-8"))
    result_id = envelope["payload"]["fields"]["result_id"]
    store, persistence, _save, queries = _stack(tmp_path / "rev1")
    store.artifact_root.mkdir(parents=True)
    artifact_path = store.artifact_root / ResultArtifactStore.artifact_name_for(result_id)
    artifact_path.write_bytes(rev1_path.read_bytes())
    persistence.rebuild_index()
    rev1_read = queries.get(result_id)
    assert rev1_read is not None and rev1_read.schema_revision == 1
    rev1_receipt = SaveReceipt(
        result_id=result_id,
        payload_hash=str(rev1_read.payload_hash),
        artifact_location=rev1_read.artifact_location,
        persisted_at=datetime(2026, 9, 23, tzinfo=_UTC),
        index_status=IndexStatus.INDEXED,
        schema_revision=1,
    )
    revoked = _producer(tmp_path / "rev1").produce_verified_read(
        rev1_read, rev1_receipt, source_artifact_path=artifact_path
    )
    _blocked(revoked, "revision_not_rev2")

    fixture, _ = _fixture()
    execution = _execution(fixture)
    store2, _persistence2, save2, queries2 = _stack(tmp_path / "legacy-shape")
    receipt = save2.save_execution(execution)
    model = queries2.get(execution.result_id)
    assert model is not None
    legacy_shape = replace(
        model,
        execution=None,
        legacy_result=object(),
        schema_version=None,
        schema_revision=None,
        payload_hash=None,
    )
    rejected_legacy = _producer(tmp_path / "legacy-shape").produce_verified_read(
        legacy_shape,
        receipt,
        source_artifact_path=store2.artifact_root
        / str(receipt.artifact_location),
    )
    _blocked(rejected_legacy, "not_canonical_execution")


@pytest.mark.parametrize(
    ("corruption", "expected"),
    [
        ("request_snapshot", "read_model_artifact_execution_mismatch"),
        ("request_limit", "read_model_artifact_execution_mismatch"),
        ("owner_missing", "read_model_artifact_execution_mismatch"),
        ("owner_mismatch", "read_model_artifact_execution_mismatch"),
        ("result_config_hash", "read_model_artifact_execution_mismatch"),
        ("available_after_decision", "read_model_artifact_execution_mismatch"),
        ("missing_row_value", "must_be_decimal_or_int"),
        ("rank_mismatch", "rank_mismatch"),
        ("reason_text_missing", "reason_text_missing"),
        ("industry_missing", "industry_missing"),
    ],
)
def test_c1_verified_read_fails_closed_on_owner_clock_hash_and_row_gaps(
    tmp_path: Path,
    corruption: str,
    expected: str,
) -> None:
    fixture, _ = _fixture()
    execution = _execution(fixture)
    if corruption == "missing_row_value":
        assert execution.decision is not None
        object.__setattr__(execution.decision.items[0], "close_price", None)
    elif corruption == "rank_mismatch":
        assert execution.decision is not None
        object.__setattr__(execution.decision.items[1], "rank", 5)
    elif corruption == "reason_text_missing":
        assert execution.decision is not None
        object.__setattr__(execution.decision.items[0], "reason_text", " ")
    elif corruption == "industry_missing":
        assert execution.decision is not None
        object.__setattr__(execution.decision.items[0], "industry", None)
    store, _persistence, save, queries = _stack(tmp_path)
    producer = _producer(tmp_path)
    receipt = save.save_execution(execution)
    read_model = queries.get(execution.result_id)
    assert read_model is not None and read_model.execution is not None
    source = store.artifact_root / str(receipt.artifact_location)
    before = source.read_bytes()
    sealed = read_model.execution

    if corruption == "request_snapshot":
        object.__setattr__(sealed.request, "config_snapshot", None)
    elif corruption == "request_limit":
        object.__setattr__(sealed.request, "max_stocks", 99)
    elif corruption == "owner_missing":
        object.__setattr__(sealed.context, "strategy_identity", None)
    elif corruption == "owner_mismatch":
        assert sealed.context.strategy_identity is not None
        object.__setattr__(
            sealed.context.strategy_identity,
            "strategy_config_hash",
            "sha256:" + "0" * 64,
        )
    elif corruption == "result_config_hash":
        assert sealed.context.result_config_snapshot is not None
        object.__setattr__(
            sealed.context.result_config_snapshot,
            "config_sha256",
            "sha256:" + "0" * 64,
        )
    elif corruption == "available_after_decision":
        assert sealed.context.decision_at is not None
        object.__setattr__(
            sealed.context,
            "available_at",
            sealed.context.decision_at.replace(microsecond=0) + timedelta(seconds=1),
        )
    rejected = producer.produce_verified_read(
        read_model, receipt, source_artifact_path=source
    )
    _blocked(rejected, expected)
    assert source.read_bytes() == before
    readback = queries.get(execution.result_id)
    assert readback is not None and readback.execution is not None
    expected_close_price = (
        None if corruption == "missing_row_value" else Decimal("100.2500")
    )
    assert readback.execution.items[0].close_price == expected_close_price


@pytest.mark.parametrize("tamper", ["row", "result_id", "clock"])
def test_c1_forged_read_model_execution_must_match_saved_artifact(
    tmp_path: Path,
    tamper: str,
) -> None:
    fixture, _ = _fixture()
    execution = _execution(fixture)
    store, _persistence, save, queries = _stack(tmp_path)
    producer = _producer(tmp_path)
    receipt = save.save_execution(execution)
    read_model = queries.get(execution.result_id)
    assert read_model is not None and read_model.execution is not None
    source = store.artifact_root / str(receipt.artifact_location)
    original_bytes = source.read_bytes()
    forged_execution = read_model.execution

    if tamper == "row":
        assert forged_execution.decision is not None
        items = list(forged_execution.decision.items)
        items[0] = replace(items[0], reason_text="forged-reason")
        forged_execution = replace(
            forged_execution,
            decision=replace(forged_execution.decision, items=tuple(items)),
        )
    elif tamper == "result_id":
        forged_execution = replace(forged_execution, result_id="another-execution-id")
    elif tamper == "clock":
        assert forged_execution.context.decision_at is not None
        forged_context = replace(
            forged_execution.context,
            decision_at=forged_execution.context.decision_at + timedelta(seconds=1),
        )
        forged_execution = replace(forged_execution, context=forged_context)
    forged_read_model = replace(read_model, execution=forged_execution)

    rejected = producer.produce_verified_read(
        forged_read_model,
        receipt,
        source_artifact_path=source,
    )
    _blocked(
        rejected,
        "result_id_mismatch" if tamper == "result_id" else "read_model_artifact_execution_mismatch",
    )
    assert forged_read_model.raw_artifact_sha256 == read_model.raw_artifact_sha256
    assert forged_read_model.payload_hash == read_model.payload_hash
    assert forged_read_model.artifact_location == read_model.artifact_location
    assert source.read_bytes() == original_bytes


def test_c1_verified_consumer_failure_preserves_saved_recommendation_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, _ = _fixture()
    execution = _execution(fixture)
    store, _persistence, save, queries = _stack(tmp_path)
    producer = _producer(tmp_path)
    receipt = save.save_execution(execution)
    read_model = queries.get(execution.result_id)
    assert read_model is not None
    source = store.artifact_root / str(receipt.artifact_location)
    original_bytes = source.read_bytes()
    monkeypatch.setattr(
        producer,
        "_produce_source",
        Mock(side_effect=OSError("synthetic forward packet write failure")),
    )

    with pytest.raises(OSError, match="synthetic forward packet write failure"):
        producer.produce_verified_read(
            read_model,
            receipt,
            source_artifact_path=source,
        )
    assert source.read_bytes() == original_bytes


def test_c1_ml_binding_requires_u4_verified_projection_readback(tmp_path: Path) -> None:
    fixture, _ = _fixture()
    execution = _execution(fixture, include_ml_binding=True)
    store, _persistence, save, queries = _stack(tmp_path)
    producer = _producer(tmp_path)
    receipt = save.save_execution(execution)
    read_model = queries.get(execution.result_id)
    assert read_model is not None
    assert read_model.ml_read_status == "unavailable"
    source = store.artifact_root / str(receipt.artifact_location)
    before = source.read_bytes()

    rejected = producer.produce_verified_read(
        read_model, receipt, source_artifact_path=source
    )
    _blocked(rejected, "ml_readback_not_verified")
    assert source.read_bytes() == before
