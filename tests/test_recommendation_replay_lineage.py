"""R020 replay lineage sidecar 的 synthetic contract/codec tests。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app_module.recommendation.codec import decode_execution_envelope, encode_execution
from app_module.recommendation.contracts import (
    Context,
    DecisionBatch,
    ExecutionStatus,
    IndexStatus,
    RecommendationExecution,
    QualityReport,
    ReferenceKind,
    Request,
    SaveReceipt,
    VersionReference,
)
from app_module.recommendation.replay_lineage import (
    REPLAY_LINEAGE_SCHEMA_REVISION,
    REPLAY_LINEAGE_SCHEMA_VERSION,
    ReplayDataSnapshotStatusV1,
    ReplayLineageChildV1,
    ReplayLineageCodecError,
    ReplayLineageSidecarV1,
    decode_replay_lineage,
    decode_replay_lineage_envelope,
    encode_replay_lineage,
)
from decision_module.recommendation.contracts import RecommendationItem


def _execution(
    *,
    result_id: str,
    parent_result_id: str,
    as_of_date: date,
    data_snapshot_refs: tuple[VersionReference, ...] = (),
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
) -> RecommendationExecution:
    return RecommendationExecution(
        result_id=result_id,
        request=Request(as_of_date=as_of_date),
        context=Context(
            as_of_date=as_of_date,
            data_snapshot_refs=data_snapshot_refs,
        ),
        status=status,
        decision=(
            DecisionBatch(items=(RecommendationItem(stock_code="2330", rule_score=Decimal("82.5")),))
            if status is ExecutionStatus.COMPLETED
            else None
        ),
        quality=QualityReport(),
        related_references=(
            VersionReference(
                kind=ReferenceKind.REPLAY_PARENT,
                reference_id=parent_result_id,
            ),
        ),
        failure_reason=None if status is ExecutionStatus.COMPLETED else "synthetic failure",
    )


def _receipt_for(execution: RecommendationExecution) -> SaveReceipt:
    envelope = decode_execution_envelope(encode_execution(execution))
    return SaveReceipt(
        result_id=execution.result_id,
        payload_hash=envelope.payload_hash,
        artifact_location=f"synthetic/{execution.result_id}.json",
        persisted_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
        index_status=IndexStatus.INDEXED,
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _rehash_document(document: dict[str, object]) -> bytes:
    body = {
        "schema_version": document["schema_version"],
        "schema_revision": document["schema_revision"],
        "payload": document["payload"],
    }
    document["payload_hash"] = "sha256:" + hashlib.sha256(_canonical_json(body)).hexdigest()
    return _canonical_json(document)


def test_lineage_sidecar_sorts_children_and_roundtrips_codec_and_receipt_hashes() -> None:
    parent_result_id = "replay-parent-r020-synthetic"
    data_ref = VersionReference(
        ReferenceKind.DATA_SNAPSHOT,
        "market-data-2026-09-22",
        "v3",
    )
    later_execution = _execution(
        result_id="replay-child-20260922",
        parent_result_id=parent_result_id,
        as_of_date=date(2026, 9, 22),
        data_snapshot_refs=(data_ref, data_ref),
    )
    earlier_execution = _execution(
        result_id="replay-child-20260915",
        parent_result_id=parent_result_id,
        as_of_date=date(2026, 9, 15),
    )
    later_receipt = _receipt_for(later_execution)
    earlier_receipt = _receipt_for(earlier_execution)

    sidecar = ReplayLineageSidecarV1(
        parent_result_id=parent_result_id,
        children=(
            ReplayLineageChildV1.from_execution(
                later_execution,
                snapshot_date=date(2026, 9, 22),
                receipt=later_receipt,
            ),
            ReplayLineageChildV1.from_execution(
                earlier_execution,
                snapshot_date=date(2026, 9, 15),
                receipt=earlier_receipt,
            ),
        ),
    )

    assert [child.snapshot_date for child in sidecar.children] == [
        date(2026, 9, 15),
        date(2026, 9, 22),
    ]
    assert sidecar.children[0].data_snapshot_status is ReplayDataSnapshotStatusV1.UNAVAILABLE
    assert sidecar.children[0].data_snapshot_refs == ()
    assert sidecar.children[1].data_snapshot_status is ReplayDataSnapshotStatusV1.AVAILABLE
    assert sidecar.children[1].data_snapshot_refs == (data_ref, data_ref)
    assert sidecar.children[0].canonical_payload_sha256 == earlier_receipt.payload_hash
    assert sidecar.children[1].canonical_payload_sha256 == later_receipt.payload_hash

    first_bytes = encode_replay_lineage(sidecar)
    second_bytes = encode_replay_lineage(sidecar)
    assert first_bytes == second_bytes
    envelope = decode_replay_lineage_envelope(first_bytes)
    assert envelope.sidecar == sidecar
    assert envelope.schema_version == REPLAY_LINEAGE_SCHEMA_VERSION
    assert envelope.schema_revision == REPLAY_LINEAGE_SCHEMA_REVISION
    assert envelope.raw_payload == first_bytes
    assert envelope.raw_payload_sha256 == "sha256:" + hashlib.sha256(first_bytes).hexdigest()
    assert decode_replay_lineage(first_bytes) == sidecar

    document = json.loads(first_bytes.decode("utf-8"))
    assert "registry_run_id" not in document
    assert "run_id" not in document["payload"]
    assert document["payload"]["parent_result_id"] == parent_result_id
    assert document["payload"]["children"][0]["data_snapshot_status"] == "unavailable"


def test_child_factory_uses_execution_parent_and_checks_optional_receipt() -> None:
    parent_result_id = "replay-parent-r020-receipt"
    execution = _execution(
        result_id="replay-child-r020-receipt",
        parent_result_id=parent_result_id,
        as_of_date=date(2026, 9, 23),
    )
    receipt = _receipt_for(execution)

    child = ReplayLineageChildV1.from_execution(
        execution,
        snapshot_date=date(2026, 9, 23),
        receipt=receipt,
    )

    assert child.result_id == execution.result_id
    assert child.replay_parent_ref == execution.related_references[0]
    assert child.replay_parent_ref.reference_id == parent_result_id
    assert child.canonical_payload_sha256 == receipt.payload_hash

    with pytest.raises(ValueError, match="result_id"):
        ReplayLineageChildV1.from_execution(
            execution,
            snapshot_date=date(2026, 9, 23),
            receipt=replace(receipt, result_id="other-child"),
        )
    with pytest.raises(ValueError, match="payload_hash"):
        ReplayLineageChildV1.from_execution(
            execution,
            snapshot_date=date(2026, 9, 23),
            receipt=replace(receipt, payload_hash="sha256:" + "0" * 64),
        )
    with pytest.raises(ValueError, match="schema version/revision"):
        ReplayLineageChildV1.from_execution(
            execution,
            snapshot_date=date(2026, 9, 23),
            receipt=replace(receipt, schema_revision=1),
        )


def test_child_readback_verifies_actual_artifact_bytes_receipt_and_identity() -> None:
    parent_result_id = "replay-parent-r020-readback"
    execution = _execution(
        result_id="replay-child-r020-readback",
        parent_result_id=parent_result_id,
        as_of_date=date(2026, 9, 23),
        data_snapshot_refs=(
            VersionReference(ReferenceKind.DATA_SNAPSHOT, "market-r020-readback", "v1"),
        ),
    )
    receipt = _receipt_for(execution)
    child = ReplayLineageChildV1.from_execution(
        execution,
        snapshot_date=date(2026, 9, 23),
        receipt=receipt,
    )

    artifact = encode_execution(execution)
    assert child.verify_execution_artifact(artifact, receipt=receipt) == execution

    changed_execution = replace(
        execution,
        decision=DecisionBatch(
            items=(RecommendationItem(stock_code="2330", rule_score=Decimal("83.5")),)
        ),
    )
    changed_artifact = encode_execution(changed_execution)
    changed_receipt = _receipt_for(changed_execution)
    with pytest.raises(ReplayLineageCodecError, match="payload hash"):
        child.verify_execution_artifact(changed_artifact)
    with pytest.raises(ReplayLineageCodecError, match="payload hash"):
        child.verify_execution_artifact(changed_artifact, receipt=changed_receipt)

    wrong_parent = replace(
        child,
        replay_parent_ref=VersionReference(
            ReferenceKind.REPLAY_PARENT,
            "replay-parent-r020-other",
        ),
    )
    with pytest.raises(ReplayLineageCodecError, match="REPLAY_PARENT"):
        wrong_parent.verify_execution_artifact(artifact)

    with pytest.raises(ReplayLineageCodecError, match="SaveReceipt.payload_hash"):
        child.verify_execution_artifact(
            artifact,
            receipt=replace(receipt, payload_hash="sha256:" + "0" * 64),
        )
    with pytest.raises(ReplayLineageCodecError, match="schema version/revision"):
        child.verify_execution_artifact(
            artifact,
            receipt=replace(receipt, schema_revision=1),
        )

    with pytest.raises(ReplayLineageCodecError, match="non-canonical|canonical"):
        child.verify_execution_artifact(artifact + b" ")


def test_factory_rejects_noncompleted_or_wrong_date_or_missing_parent_child() -> None:
    completed = _execution(
        result_id="replay-child-r020-valid",
        parent_result_id="replay-parent-r020-valid",
        as_of_date=date(2026, 9, 24),
    )
    with pytest.raises(ValueError, match="context.as_of_date"):
        ReplayLineageChildV1.from_execution(
            completed,
            snapshot_date=date(2026, 9, 23),
        )

    failed = _execution(
        result_id="replay-child-r020-failed",
        parent_result_id="replay-parent-r020-valid",
        as_of_date=date(2026, 9, 24),
        status=ExecutionStatus.FAILED,
    )
    with pytest.raises(ValueError, match="completed execution"):
        ReplayLineageChildV1.from_execution(
            failed,
            snapshot_date=date(2026, 9, 24),
        )

    no_parent = replace(completed, related_references=())
    with pytest.raises(ValueError, match="REPLAY_PARENT"):
        ReplayLineageChildV1.from_execution(
            no_parent,
            snapshot_date=date(2026, 9, 24),
        )

    duplicate_parent = replace(
        completed,
        related_references=completed.related_references * 2,
    )
    with pytest.raises(ValueError, match="恰有一個 REPLAY_PARENT"):
        ReplayLineageChildV1.from_execution(
            duplicate_parent,
            snapshot_date=date(2026, 9, 24),
        )


def test_sidecar_requires_unique_children_and_consistent_parent_reference() -> None:
    parent_result_id = "replay-parent-r020-unique"
    execution = _execution(
        result_id="replay-child-r020-unique",
        parent_result_id=parent_result_id,
        as_of_date=date(2026, 9, 22),
    )
    child = ReplayLineageChildV1.from_execution(
        execution,
        snapshot_date=date(2026, 9, 22),
    )

    with pytest.raises(ValueError, match="不可重複"):
        ReplayLineageSidecarV1(
            parent_result_id=parent_result_id,
            children=(child, child),
        )
    same_day_child = ReplayLineageChildV1.from_execution(
        _execution(
            result_id="replay-child-r020-same-day",
            parent_result_id=parent_result_id,
            as_of_date=date(2026, 9, 22),
        ),
        snapshot_date=date(2026, 9, 22),
    )
    with pytest.raises(ValueError, match="每個 snapshot_date"):
        ReplayLineageSidecarV1(
            parent_result_id=parent_result_id,
            children=(child, same_day_child),
        )
    with pytest.raises(ValueError, match="不可與 child"):
        ReplayLineageSidecarV1(
            parent_result_id=child.result_id,
            children=(child,),
        )
    with pytest.raises(ValueError, match="必須符合 parent_result_id"):
        ReplayLineageSidecarV1(
            parent_result_id="replay-parent-r020-other",
            children=(child,),
        )
    with pytest.raises(ValueError, match="replay_parent"):
        ReplayLineageChildV1(
            snapshot_date=child.snapshot_date,
            result_id=child.result_id,
            canonical_payload_sha256=child.canonical_payload_sha256,
            replay_parent_ref=VersionReference(
                ReferenceKind.RUNTIME_RUN,
                parent_result_id,
            ),
            data_snapshot_status=ReplayDataSnapshotStatusV1.UNAVAILABLE,
        )


def test_parent_without_child_snapshots_has_a_valid_empty_sidecar() -> None:
    sidecar = ReplayLineageSidecarV1(
        parent_result_id="replay-parent-r020-no-snapshots",
    )

    assert sidecar.children == ()
    assert decode_replay_lineage(encode_replay_lineage(sidecar)) == sidecar


def test_data_snapshot_status_and_reference_kind_are_explicit() -> None:
    parent_result_id = "replay-parent-r020-data"
    execution = _execution(
        result_id="replay-child-r020-data",
        parent_result_id=parent_result_id,
        as_of_date=date(2026, 9, 22),
    )
    child = ReplayLineageChildV1.from_execution(
        execution,
        snapshot_date=date(2026, 9, 22),
    )
    data_ref = VersionReference(ReferenceKind.DATA_SNAPSHOT, "market-snapshot")

    with pytest.raises(ValueError, match="至少一個 reference"):
        replace(
            child,
            data_snapshot_status=ReplayDataSnapshotStatusV1.AVAILABLE,
        )
    with pytest.raises(ValueError, match="不可包含 references"):
        replace(
            child,
            data_snapshot_refs=(data_ref,),
        )
    with pytest.raises(ValueError, match="只接受 data_snapshot"):
        replace(
            child,
            data_snapshot_status=ReplayDataSnapshotStatusV1.AVAILABLE,
            data_snapshot_refs=(
                VersionReference(ReferenceKind.RUNTIME_RUN, "not-a-data-snapshot"),
            ),
        )


def test_decoder_rejects_hash_tampering_unknown_schema_and_noncanonical_bytes() -> None:
    execution = _execution(
        result_id="replay-child-r020-tamper",
        parent_result_id="replay-parent-r020-tamper",
        as_of_date=date(2026, 9, 22),
    )
    child = ReplayLineageChildV1.from_execution(
        execution,
        snapshot_date=date(2026, 9, 22),
    )
    raw = encode_replay_lineage(
        ReplayLineageSidecarV1(
            parent_result_id="replay-parent-r020-tamper",
            children=(child,),
        )
    )
    document = json.loads(raw.decode("utf-8"))

    tampered = json.loads(raw.decode("utf-8"))
    tampered["payload"]["children"][0]["result_id"] = "replay-child-tampered"
    with pytest.raises(ReplayLineageCodecError, match="hash 不符"):
        decode_replay_lineage(_canonical_json(tampered))

    unknown_version = json.loads(raw.decode("utf-8"))
    unknown_version["schema_version"] = "recommendation-replay-lineage.v99"
    with pytest.raises(ReplayLineageCodecError, match="hash 不符"):
        decode_replay_lineage(_canonical_json(unknown_version))
    with pytest.raises(ReplayLineageCodecError, match="不支援 schema_version"):
        decode_replay_lineage(_rehash_document(unknown_version))

    unknown_revision = json.loads(raw.decode("utf-8"))
    unknown_revision["schema_revision"] = REPLAY_LINEAGE_SCHEMA_REVISION + 1
    with pytest.raises(ReplayLineageCodecError, match="不支援 schema_revision"):
        decode_replay_lineage(_rehash_document(unknown_revision))

    malformed_hash = json.loads(raw.decode("utf-8"))
    malformed_hash["payload_hash"] = "not-a-sha256"
    with pytest.raises(ReplayLineageCodecError, match="小寫 sha256"):
        decode_replay_lineage(_canonical_json(malformed_hash))

    pretty_bytes = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8")
    with pytest.raises(ReplayLineageCodecError, match="canonical UTF-8 JSON"):
        decode_replay_lineage(pretty_bytes)


@pytest.mark.parametrize(
    "raw_payload",
    [
        b'{"schema_version":"recommendation-replay-lineage.v1","schema_version":"x"}',
        b'{"payload":NaN}',
        b"\xff",
    ],
)
def test_decoder_rejects_duplicate_keys_nonfinite_constants_and_invalid_utf8(
    raw_payload: bytes,
) -> None:
    with pytest.raises(ReplayLineageCodecError):
        decode_replay_lineage(raw_payload)


def test_decoder_rejects_unknown_fields_and_parent_reference_mismatch() -> None:
    execution = _execution(
        result_id="replay-child-r020-strict",
        parent_result_id="replay-parent-r020-strict",
        as_of_date=date(2026, 9, 22),
    )
    child = ReplayLineageChildV1.from_execution(
        execution,
        snapshot_date=date(2026, 9, 22),
    )
    raw = encode_replay_lineage(
        ReplayLineageSidecarV1(
            parent_result_id="replay-parent-r020-strict",
            children=(child,),
        )
    )

    unknown = json.loads(raw.decode("utf-8"))
    unknown["payload"]["registry_run_id"] = "ui-registry-run"
    with pytest.raises(ReplayLineageCodecError, match="未知欄位"):
        decode_replay_lineage(_rehash_document(unknown))

    mismatch = json.loads(raw.decode("utf-8"))
    mismatch["payload"]["parent_result_id"] = "another-parent"
    with pytest.raises(ReplayLineageCodecError, match="hash 不符"):
        decode_replay_lineage(_canonical_json(mismatch))
    mismatch_bytes = _rehash_document(mismatch)
    with pytest.raises(ReplayLineageCodecError, match="parent_result_id"):
        decode_replay_lineage(mismatch_bytes)


def test_decoder_rejects_validly_hashed_children_in_nonchronological_order() -> None:
    parent_result_id = "replay-parent-r020-order"
    children = tuple(
        ReplayLineageChildV1.from_execution(
            _execution(
                result_id=f"replay-child-{day}",
                parent_result_id=parent_result_id,
                as_of_date=date(2026, 9, day),
            ),
            snapshot_date=date(2026, 9, day),
        )
        for day in (15, 22)
    )
    raw = encode_replay_lineage(
        ReplayLineageSidecarV1(
            parent_result_id=parent_result_id,
            children=children,
        )
    )
    reversed_document = json.loads(raw.decode("utf-8"))
    reversed_document["payload"]["children"].reverse()

    with pytest.raises(ReplayLineageCodecError, match="canonical UTF-8 JSON"):
        decode_replay_lineage(_rehash_document(reversed_document))
