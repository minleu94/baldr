"""C1 SCHEMA-P/N：rev1 歷史 bytes 經 U4 唯一 read seam 的相容性。"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app_module.recommendation.codec import (
    decode_execution_envelope,
    ExecutionCodecError,
)
from app_module.recommendation.persistence import (
    ExecutionArtifactIntegrityError,
    RecommendationExecutionPersistence,
)
from app_module.recommendation.queries import RecommendationExecutionQueries
from data_module.result_artifact_store import (
    ArtifactIndexMetadata,
    ResultArtifactStore,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "c1_cross_boundary"
REV1_RAW_SHA256 = "sha256:dbd3c2194ef53c2fee3e41e772187d2453c52237328aa179833282e0cc76a52b"
REV1_PAYLOAD_HASH = "sha256:db61aabb2b388609d49c9daae77ee54ae389a51c9f12acd59f329a7f1cf265b5"


def _fixture_manifest() -> dict[str, Any]:
    return json.loads(
        (FIXTURE_ROOT / "fixture_manifest.json").read_text(encoding="utf-8")
    )


def _stack(tmp_path: Path) -> tuple[ResultArtifactStore, RecommendationExecutionPersistence, RecommendationExecutionQueries]:
    runs_dir = tmp_path / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)
    return store, persistence, RecommendationExecutionQueries(persistence)


def _canonical_bytes(document: dict[str, Any]) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _rehash_envelope(document: dict[str, Any]) -> bytes:
    hash_material = {
        "schema_version": document["schema_version"],
        "schema_revision": document["schema_revision"],
        "payload": document["payload"],
    }
    document["payload_hash"] = "sha256:" + hashlib.sha256(
        _canonical_bytes(hash_material)
    ).hexdigest()
    return _canonical_bytes(document)


def _metadata(raw: bytes, document: dict[str, Any]) -> ArtifactIndexMetadata:
    payload = document["payload"]
    assert isinstance(payload, dict)
    fields = payload["fields"]
    assert isinstance(fields, dict)
    return ArtifactIndexMetadata(
        result_id=str(fields["result_id"]),
        payload_hash=str(document["payload_hash"]),
        artifact_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
        schema_version=str(document["schema_version"]),
        schema_revision=document["schema_revision"],
        label="C1 synthetic schema fixture",
        notes="cross-boundary readback test",
        persisted_at="2026-09-23T00:00:00+00:00",
    )


def test_c1_schema_rev1_is_read_through_u4_without_changing_bytes_or_unknowns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _fixture_manifest()
    entry = next(
        item
        for item in manifest["entries"]
        if item["fixture_id"] == "c1_cross_boundary_schema_rev1"
    )
    raw = (FIXTURE_ROOT / str(entry["file"])).read_bytes()
    assert len(raw) == entry["byte_length"] == 5_033
    assert "sha256:" + hashlib.sha256(raw).hexdigest() == REV1_RAW_SHA256
    assert entry["sha256"] == REV1_RAW_SHA256

    envelope = decode_execution_envelope(raw)
    execution = envelope.execution
    assert envelope.schema_version == "recommendation-execution.v1"
    assert envelope.schema_revision == 1
    assert envelope.payload_hash == REV1_PAYLOAD_HASH
    assert envelope.raw_payload_sha256 == REV1_RAW_SHA256
    assert envelope.raw_payload == raw

    # rev1 已有決策時間保留原 timezone/value；rev1 真缺的新欄位維持 unknown。
    assert execution.context.decision_at == datetime.fromisoformat(
        "2026-09-22T09:05:06+08:00"
    )
    assert execution.request.config_snapshot is None
    assert execution.context.result_config_snapshot is None
    assert execution.context.snapshot_cohort is None
    assert execution.context.strategy_identity is None
    assert execution.context.universe_identity is None
    assert execution.context.evidence_identity is None
    assert execution.context.created_at is None
    assert execution.context.available_at is None

    store, persistence, queries = _stack(tmp_path)
    metadata = _metadata(raw, json.loads(raw.decode("utf-8")))
    store.publish_artifact(raw, metadata)
    assert persistence.rebuild_index() == (execution.result_id,)

    def reject_reencode(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("rev1 readback must not invoke the rev2 writer")

    monkeypatch.setattr(
        "app_module.recommendation.persistence.encode_execution", reject_reencode
    )
    loaded = queries.get(execution.result_id)

    assert loaded is not None
    assert loaded.execution == execution
    assert loaded.schema_version == envelope.schema_version
    assert loaded.schema_revision == 1
    assert loaded.payload_hash == REV1_PAYLOAD_HASH
    assert loaded.raw_artifact_sha256 == REV1_RAW_SHA256
    assert loaded.integrity_basis == "canonical_payload_and_index_verified"
    assert loaded.execution.context.decision_at == execution.context.decision_at
    assert loaded.execution.context.result_config_snapshot is None
    assert store.read_artifact(execution.result_id) == raw
    assert (
        store.artifact_root / store.artifact_name_for(execution.result_id)
    ).read_bytes() == raw


@pytest.mark.parametrize(
    "mutation",
    ("schema_version", "schema_revision", "record_type", "payload_hash"),
)
def test_c1_schema_unknown_header_type_or_hash_fails_closed_and_keeps_input_bytes(
    tmp_path: Path,
    mutation: str,
) -> None:
    valid_raw = (FIXTURE_ROOT / "schema_rev1.json").read_bytes()
    document = json.loads(valid_raw.decode("utf-8"))
    assert isinstance(document, dict)

    if mutation == "schema_version":
        document["schema_version"] = "recommendation-execution.v999"
        bad_raw = _rehash_envelope(document)
    elif mutation == "schema_revision":
        document["schema_revision"] = 99
        bad_raw = _rehash_envelope(document)
    elif mutation == "record_type":
        payload = document["payload"]
        assert isinstance(payload, dict)
        payload["$record"] = "recommendation.execution.unknown.v999"
        bad_raw = _rehash_envelope(document)
    else:
        document["payload_hash"] = "sha256:" + ("0" * 64)
        bad_raw = _canonical_bytes(document)

    assert bad_raw != valid_raw
    store, _, queries = _stack(tmp_path)
    metadata = _metadata(bad_raw, document)
    store.publish_artifact(bad_raw, metadata)
    store.index_artifact(metadata)
    artifact_path = store.artifact_root / store.artifact_name_for(metadata.result_id)

    with pytest.raises((ExecutionArtifactIntegrityError, ExecutionCodecError)):
        queries.get(metadata.result_id)

    assert artifact_path.read_bytes() == bad_raw
    assert store.read_artifact(metadata.result_id) == bad_raw
