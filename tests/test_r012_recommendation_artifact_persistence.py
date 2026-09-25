"""R012 create-only execution persistence; every artifact stays under tmp_path."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import ast
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from threading import Barrier, Event
from typing import Any

import pytest

from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.recommendation.persistence import (
    ExecutionArtifactIntegrityError,
    ExecutionArtifactWriteError,
    ExecutionIdentityConflict,
    ExecutionIndexReadError,
    ExecutionIndexRebuildError,
    PartialExecutionPersistenceError,
    RecommendationExecutionPersistence,
)
from app_module.recommendation.queries import RecommendationExecutionQueries
from app_module.recommendation.save import RecommendationSaveService
from app_module.recommendation.contracts import (
    Context,
    ExecutionStatus,
    MLAvailability,
    MLAvailabilityStatus,
    MLReceiptBinding,
    RecommendationExecution,
    ReferenceKind,
    Request,
    VersionReference,
)
from app_module.recommendation.codec import encode_execution
from app_module.recommendation_repository import RecommendationRepository
from data_module.contracts.market import SourceRef
from data_module.result_artifact_store import (
    ArtifactIndexMetadata,
    ResultArtifactIndexError,
    ResultArtifactIntegrityError,
    ResultArtifactPublishError,
    ResultArtifactStore,
)
from decision_module.recommendation.contracts import (
    DecisionBatch,
    RecommendationItem,
    UniverseReference,
)


class _TmpConfig:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root

    def resolve_output_path(self, subfolder: str) -> Path:
        path = self.output_root / subfolder
        path.mkdir(parents=True, exist_ok=True)
        return path


def _ref(kind: ReferenceKind, reference_id: str) -> VersionReference:
    return VersionReference(kind, reference_id, version="v1")


def _execution(
    result_id: str = "r012-result-A",
    *,
    score: Decimal = Decimal("91.2300"),
    source_snapshot: str = "snapshot-A",
    regime: str = "Trend",
) -> RecommendationExecution:
    as_of = date(2026, 9, 22)
    source_ref = SourceRef("daily-prices", revision=7, snapshot_id=source_snapshot)
    item = RecommendationItem(
        stock_code="2330",
        rule_score=score,
        rank=0,
        universe_ref=UniverseReference(
            policy_id="listed-v1",
            snapshot_id=f"members-{source_snapshot}",
            as_of_date=as_of,
            members_hash="members-hash",
        ),
        reasons=("eligible",),
        stock_name="台積電",
        regime_match=True,
    )
    projection_ref = _ref(ReferenceKind.ML_PROJECTION, "projection-A")
    receipt_ref = _ref(ReferenceKind.ML_RECEIPT, "receipt-A")
    receipt = MLReceiptBinding(
        receipt_ref=receipt_ref,
        receipt_hash="sha256:" + "a" * 64,
        result_id=result_id,
        decision_date=as_of,
        model_candidate_id="candidate-A",
        projected_stock_codes=("2330",),
        cost_scenario_hash="sha256:" + "b" * 64,
    )
    return RecommendationExecution(
        result_id=result_id,
        request=Request(
            as_of_date=as_of,
            config_ref=_ref(ReferenceKind.CONFIG, "config-A"),
            profile_ref=_ref(ReferenceKind.PROFILE, "profile-A"),
        ),
        context=Context(
            as_of_date=as_of,
            decision_at=datetime(2026, 9, 22, 9, 5, tzinfo=timezone(timedelta(hours=8))),
            source_refs=(source_ref,),
            config_ref=_ref(ReferenceKind.CONFIG, "config-A"),
            profile_ref=_ref(ReferenceKind.PROFILE, "profile-A"),
            algorithm_ref=_ref(ReferenceKind.ALGORITHM, "algorithm-A"),
            warnings=(f"captured:{source_snapshot}",),
        ),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=(item,), regime=regime),
        ml_availability=MLAvailability(status=MLAvailabilityStatus.AVAILABLE),
        ml_projection_refs=(projection_ref,),
        ml_receipt_refs=(receipt,),
    )


def _stack(tmp_path: Path) -> tuple[ResultArtifactStore, RecommendationExecutionPersistence, RecommendationSaveService, RecommendationExecutionQueries]:
    runs_dir = tmp_path / "output" / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)
    save = RecommendationSaveService(persistence)
    queries = RecommendationExecutionQueries(persistence)
    return store, persistence, save, queries


def _under(root: Path, *paths: Path) -> None:
    resolved_root = root.resolve()
    for path in paths:
        assert path.resolve().is_relative_to(resolved_root), path


def _envelope(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw.decode("utf-8"))
    assert isinstance(value, dict)
    return value


def _rehash_envelope(document: dict[str, Any]) -> bytes:
    header = {
        "schema_version": document["schema_version"],
        "schema_revision": document["schema_revision"],
        "payload": document["payload"],
    }
    canonical = json.dumps(
        header,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    document["payload_hash"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def test_r012_save_query_keeps_opaque_id_and_exact_receipt_projection_refs(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("Opaque:/Mixed/ID.  ")
    receipt = save.save_execution(
        execution,
        label="R012 原始名稱",
        notes="saved from sealed execution",
        now=lambda: datetime(2026, 9, 23, 12, tzinfo=timezone.utc),
    )

    loaded = queries.get(execution.result_id)
    assert loaded is not None
    assert loaded.execution == execution
    assert loaded.execution.result_id == "Opaque:/Mixed/ID.  "
    assert loaded.execution.ml_projection_refs == execution.ml_projection_refs
    assert loaded.execution.ml_receipt_refs == execution.ml_receipt_refs
    assert loaded.payload_hash == receipt.payload_hash
    assert loaded.label == "R012 原始名稱"
    assert loaded.notes == "saved from sealed execution"
    artifact = store.artifact_root / store.artifact_name_for(execution.result_id)
    _under(tmp_path, artifact, store.database_path)
    assert artifact.read_bytes() == encode_execution(execution)


def test_r012_filename_mapping_separates_windows_collisions_and_traversal_ids(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    ids = ("CON", "con", "CON.", "con ", "Case", "case", "../outside", r"..\outside")
    names = {store.artifact_name_for(value) for value in ids}
    assert len(names) == len(ids)
    assert all(len(name) == 69 and name.endswith(".json") for name in names)

    traversal_id = "../outside"
    save.save_execution(_execution(traversal_id))
    loaded = queries.get(traversal_id)
    assert loaded is not None and loaded.execution.result_id == traversal_id
    artifact = store.artifact_root / store.artifact_name_for(traversal_id)
    _under(tmp_path, artifact)
    assert not (tmp_path / "output" / "recommendation" / "outside.json").exists()


@pytest.mark.parametrize(
    ("artifact_relative", "database_relative"),
    (
        (Path("runs/execution_artifacts"), Path("runs/other.db")),
        (Path("runs/other_artifacts"), Path("runs/recommendation_runs.db")),
        (Path("runs/Execution_Artifacts"), Path("runs/recommendation_runs.db")),
        (Path("runs/execution_artifacts"), Path("runs/RECOMMENDATION_RUNS.DB")),
        (Path("Runs/execution_artifacts"), Path("Runs/recommendation_runs.db")),
        (
            Path("runs-a/execution_artifacts"),
            Path("runs-b/recommendation_runs.db"),
        ),
    ),
)
def test_r012_store_rejects_layouts_that_break_legacy_identity_interlock(
    tmp_path: Path,
    artifact_relative: Path,
    database_relative: Path,
) -> None:
    with pytest.raises(ValueError, match="同一 runs 目錄"):
        ResultArtifactStore(
            tmp_path / artifact_relative,
            tmp_path / database_relative,
    )
    assert tuple(tmp_path.iterdir()) == ()


def test_r012_same_id_same_hash_is_idempotent_and_does_not_rename_metadata(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("r012-idempotent")
    first_time = datetime(2026, 9, 23, 10, tzinfo=timezone.utc)
    first = save.save_execution(
        execution, label="first label", notes="first notes", now=lambda: first_time
    )
    raw = store.read_artifact(execution.result_id)
    second = save.save_execution(
        execution,
        label="ignored repeated label",
        notes="ignored repeated notes",
        now=lambda: datetime(2026, 9, 24, tzinfo=timezone.utc),
    )
    loaded = queries.get(execution.result_id)
    assert raw is not None and store.read_artifact(execution.result_id) == raw
    assert first.payload_hash == second.payload_hash
    assert first.persisted_at == second.persisted_at == first_time
    assert loaded is not None
    assert (loaded.label, loaded.notes) == ("first label", "first notes")
    assert len(queries.list()) == 1


def test_r012_same_id_different_hash_is_hard_conflict_and_preserves_first_bytes(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    first_execution = _execution("r012-conflict", score=Decimal("10.00"))
    first_receipt = save.save_execution(first_execution)
    raw_before = store.read_artifact(first_execution.result_id)

    with pytest.raises(ExecutionIdentityConflict):
        save.save_execution(_execution("r012-conflict", score=Decimal("11.00")))

    assert store.read_artifact(first_execution.result_id) == raw_before
    loaded = queries.get(first_execution.result_id)
    assert loaded is not None
    assert loaded.execution == first_execution
    assert loaded.payload_hash == first_receipt.payload_hash


def test_r012_metadata_identity_blocks_different_hash_before_republishing_missing_artifact(
    tmp_path: Path,
) -> None:
    store, _, save, _ = _stack(tmp_path)
    original = _execution("r012-metadata-authority-conflict")
    save.save_execution(original)
    artifact_path = store.artifact_root / store.artifact_name_for(original.result_id)
    artifact_path.unlink()
    connection = sqlite3.connect(store.database_path)
    try:
        connection.execute(
            "DELETE FROM result_artifact_index WHERE result_id = ?",
            (original.result_id,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ExecutionIdentityConflict):
        save.save_execution(
            _execution(original.result_id, score=Decimal("99.00"))
        )
    assert not artifact_path.exists()


def test_r012_save_after_source_change_saves_the_sealed_execution_snapshot(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution_a = _execution(
        "r012-sealed-before-source-change",
        source_snapshot="snapshot-A",
        regime="Trend",
    )
    execution_b = _execution(
        "r012-later-execution",
        source_snapshot="snapshot-B",
        regime="Range",
    )

    save.save_execution(execution_b)
    saved_a = save.save_execution(execution_a)
    loaded_a = queries.get(execution_a.result_id)

    assert loaded_a is not None
    assert loaded_a.execution == execution_a
    assert loaded_a.execution.context.source_refs == execution_a.context.source_refs
    assert loaded_a.execution.decision == execution_a.decision
    assert loaded_a.payload_hash == saved_a.payload_hash
    assert store.read_artifact(execution_a.result_id) == encode_execution(execution_a)


def test_r012_concurrent_same_payload_create_has_one_artifact_and_index(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("r012-concurrent-identical")
    barrier = Barrier(2)

    def run_save(_: int) -> str:
        barrier.wait(timeout=10)
        return save.save_execution(execution).payload_hash

    with ThreadPoolExecutor(max_workers=2) as pool:
        payload_hashes = list(pool.map(run_save, (1, 2)))

    assert payload_hashes[0] == payload_hashes[1]
    assert len(queries.list()) == 1
    assert store.read_artifact(execution.result_id) == encode_execution(execution)
    files = tuple(store.artifact_root.glob("*.json"))
    assert len(files) == 1
    _under(tmp_path, *files)


def test_r012_concurrent_different_hash_has_one_winner_and_one_conflict(
    tmp_path: Path,
) -> None:
    _, _, save, queries = _stack(tmp_path)
    candidates = (
        _execution("r012-concurrent-conflict", score=Decimal("12.00")),
        _execution("r012-concurrent-conflict", score=Decimal("13.00")),
    )
    barrier = Barrier(2)

    def run_save(execution: RecommendationExecution) -> str:
        barrier.wait(timeout=10)
        try:
            return save.save_execution(execution).payload_hash
        except ExecutionIdentityConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(run_save, candidates))

    assert outcomes.count("conflict") == 1
    assert sum(value != "conflict" for value in outcomes) == 1
    loaded = queries.get(candidates[0].result_id)
    assert loaded is not None
    assert loaded.execution in candidates


def test_r012_index_read_failure_is_not_reported_as_artifact_or_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("r012-pre-index-read-failure")

    def fail_index_read(_: str) -> None:
        raise ResultArtifactIndexError("injected SQLite read failure")

    monkeypatch.setattr(store, "get_index", fail_index_read)
    with pytest.raises(ExecutionIndexReadError):
        save.save_execution(execution)
    assert not store.artifact_root.exists()
    monkeypatch.undo()
    assert queries.get(execution.result_id) is None


def test_r012_query_sqlite_read_failure_is_distinct_from_artifact_integrity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("r012-query-index-read-failure")
    save.save_execution(execution)

    def fail_index_read(_: str) -> None:
        raise ResultArtifactIndexError("injected SQLite read failure")

    monkeypatch.setattr(store, "get_index", fail_index_read)
    with pytest.raises(ExecutionIndexReadError):
        queries.get(execution.result_id)


def test_r012_artifact_create_failure_leaves_no_artifact_or_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("r012-file-create-failure")

    def fail_publish(payload: bytes, metadata: ArtifactIndexMetadata) -> Path:
        raise ResultArtifactPublishError("injected file create failure")

    monkeypatch.setattr(store, "publish_artifact", fail_publish)
    with pytest.raises(ExecutionArtifactWriteError):
        save.save_execution(execution)
    assert not store.artifact_root.exists()
    assert queries.get(execution.result_id) is None


def test_r012_metadata_claim_failure_keeps_orphan_reserved_from_legacy_and_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    result_id = "r012-metadata-claim-failure"
    execution = _execution(result_id)

    def fail_claim(connection: sqlite3.Connection, metadata: ArtifactIndexMetadata) -> None:
        raise sqlite3.OperationalError("injected identity metadata commit failure")

    monkeypatch.setattr(store, "_claim_identity_metadata", fail_claim)
    with pytest.raises(PartialExecutionPersistenceError):
        save.save_execution(execution)

    artifact = store.artifact_root / store.artifact_name_for(result_id)
    assert artifact.read_bytes() == encode_execution(execution)
    assert store.get_identity_payload_hash(result_id) is None
    assert store.get_index(result_id) is None
    with pytest.raises(ExecutionArtifactIntegrityError, match="canonical (?:identity metadata claim|artifact) .*index 缺失"):
        queries.get(result_id)

    legacy_repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    legacy = RecommendationResultDTO(
        result_id=result_id,
        result_name="legacy must not steal orphan",
        config={},
        recommendations=[],
        created_at="",
        notes="orphan guard",
    )
    with pytest.raises(RuntimeError, match="canonical artifact already exists"):
        legacy_repository.save_result(legacy)
    assert legacy_repository.load_result(result_id) is None

    monkeypatch.undo()
    receipt = save.save_execution(execution)
    assert receipt.index_status.value == "indexed"
    assert queries.get(result_id) is not None


def test_r012_file_create_failure_rolls_back_identity_claim_and_same_hash_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("r012-real-file-create-failure")

    def fail_link(source: Path, destination: Path, *, follow_symlinks: bool) -> None:
        raise PermissionError("injected exclusive create failure")

    monkeypatch.setattr("data_module.result_artifact_store.os.link", fail_link)
    with pytest.raises(ExecutionArtifactWriteError):
        save.save_execution(execution)
    assert tuple(store.artifact_root.glob("*.json")) == ()
    assert store.get_identity_payload_hash(execution.result_id) is None
    assert store.get_index(execution.result_id) is None
    assert queries.get(execution.result_id) is None

    monkeypatch.undo()
    assert save.save_execution(execution).index_status.value == "indexed"
    assert queries.get(execution.result_id) is not None


def test_r012_index_failure_after_durable_artifact_returns_pending_and_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("r012-file-only-after-index-failure")
    expected_bytes = encode_execution(execution)

    def fail_index(
        metadata: ArtifactIndexMetadata, *, repair_projection: bool = False
    ) -> Any:
        raise sqlite3.OperationalError("injected index commit failure")

    monkeypatch.setattr(store, "index_artifact", fail_index)
    with pytest.raises(PartialExecutionPersistenceError) as error:
        save.save_execution(execution)
    assert error.value.receipt.index_status.value == "pending"
    assert store.read_artifact(execution.result_id) == expected_bytes
    with pytest.raises(ExecutionArtifactIntegrityError, match="canonical (?:identity metadata claim|artifact) .*index 缺失"):
        queries.get(execution.result_id)

    monkeypatch.undo()
    recovered = save.save_execution(execution)
    assert recovered.index_status.value == "indexed"
    assert store.read_artifact(execution.result_id) == expected_bytes
    assert queries.get(execution.result_id) is not None


def test_r012_file_only_orphan_with_matching_id_hash_recovers_index(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("r012-orphan-recovery")
    expected = save.save_execution(execution, label="kept label", notes="kept notes")
    connection = sqlite3.connect(store.database_path)
    try:
        connection.execute(
            "DELETE FROM result_artifact_index WHERE result_id = ?",
            (execution.result_id,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ExecutionArtifactIntegrityError, match="canonical (?:identity metadata claim|artifact) .*index 缺失"):
        queries.get(execution.result_id)
    recovered = save.save_execution(execution, label="different", notes="different")
    loaded = queries.get(execution.result_id)
    assert recovered.payload_hash == expected.payload_hash
    assert loaded is not None
    assert (loaded.label, loaded.notes) == ("kept label", "kept notes")
    assert loaded.persisted_at == expected.persisted_at


def test_r012_missing_metadata_row_can_be_restored_without_losing_index(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("r012-restore-missing-metadata-row")
    save.save_execution(execution)
    connection = sqlite3.connect(store.database_path)
    try:
        connection.execute(
            "DELETE FROM result_artifact_metadata WHERE result_id = ?",
            (execution.result_id,),
        )
        connection.commit()
    finally:
        connection.close()

    restored_at = "2026-09-23T12:34:56.000000+00:00"
    raw = encode_execution(execution)
    document = _envelope(raw)
    metadata = ArtifactIndexMetadata(
        result_id=execution.result_id,
        payload_hash=str(document["payload_hash"]),
        artifact_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
        schema_version="recommendation-execution.v1",
        schema_revision=2,
        label="restored label",
        notes="restored notes",
        persisted_at=restored_at,
    )
    restored = store.restore_missing_metadata(metadata)
    loaded = queries.get(execution.result_id)

    assert restored.metadata_present
    assert restored.metadata_payload_hash == metadata.payload_hash
    assert loaded is not None
    assert (loaded.label, loaded.notes) == ("restored label", "restored notes")
    assert loaded.persisted_at == datetime.fromisoformat(restored_at)


def test_r012_explicit_projection_rebuild_removes_stale_index_only_row(
    tmp_path: Path,
) -> None:
    store, persistence, save, queries = _stack(tmp_path)
    execution = _execution("r012-valid-for-rebuild")
    save.save_execution(execution, label="authoritative label", notes="authoritative notes")
    connection = sqlite3.connect(store.database_path)
    try:
        connection.execute(
            """
            INSERT INTO result_artifact_index
            (result_id, artifact_name, payload_hash, artifact_sha256, schema_version, schema_revision)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "r012-index-only-stale",
                store.artifact_name_for("r012-index-only-stale"),
                "sha256:" + "c" * 64,
                "sha256:" + "d" * 64,
                "recommendation-execution.v1",
                1,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    assert persistence.rebuild_index() == (execution.result_id,)
    rows = queries.list()
    assert len(rows) == 1
    assert rows[0].execution == execution
    assert (rows[0].label, rows[0].notes) == ("authoritative label", "authoritative notes")


def test_r012_rebuild_serializes_inventory_with_concurrent_save_and_keeps_new_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, persistence, save, queries = _stack(tmp_path)
    execution_a = _execution("r012-rebuild-linearization-A")
    execution_b = _execution("r012-rebuild-linearization-B")
    save.save_execution(execution_a, label="A authority", notes="preserve A")

    original_iter = store.iter_artifacts
    original_publish = store.publish_artifact
    scan_barrier = Barrier(2)
    resume_barrier = Barrier(2)
    publish_barrier = Barrier(2)
    save_finished = Event()
    first_name = store.artifact_name_for(execution_a.result_id)

    def paused_inventory() -> Any:
        for artifact in original_iter():
            yield artifact
            if artifact.artifact_name == first_name:
                scan_barrier.wait(timeout=10)
                resume_barrier.wait(timeout=10)

    def synchronized_publish(
        payload: bytes, metadata: ArtifactIndexMetadata
    ) -> Path:
        publish_barrier.wait(timeout=10)
        return original_publish(payload, metadata)

    def save_b() -> Any:
        try:
            return save.save_execution(execution_b, label="B authority", notes="new save")
        finally:
            save_finished.set()

    monkeypatch.setattr(store, "iter_artifacts", paused_inventory)
    monkeypatch.setattr(store, "publish_artifact", synchronized_publish)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rebuild_future = pool.submit(persistence.rebuild_index)
        scan_barrier.wait(timeout=10)
        save_future = pool.submit(save_b)
        publish_barrier.wait(timeout=10)
        # The publisher has reached its SQLite reservation while inventory A
        # is paused.  It must wait for the rebuild writer transaction to end.
        save_waited_for_rebuild = not save_finished.wait(timeout=0.2)
        resume_barrier.wait(timeout=10)
        assert save_waited_for_rebuild
        assert rebuild_future.result(timeout=10) == (execution_a.result_id,)
        receipt_b = save_future.result(timeout=10)

    assert receipt_b.index_status.value == "indexed"
    loaded_a = queries.get(execution_a.result_id)
    loaded_b = queries.get(execution_b.result_id)
    assert loaded_a is not None and loaded_a.execution == execution_a
    assert (loaded_a.label, loaded_a.notes) == ("A authority", "preserve A")
    assert loaded_b is not None and loaded_b.execution == execution_b
    assert (loaded_b.label, loaded_b.notes) == ("B authority", "new save")


def test_r012_rebuild_reports_sqlite_write_failure_as_index_error(
    tmp_path: Path,
) -> None:
    store, persistence, save, queries = _stack(tmp_path)
    execution = _execution("r012-rebuild-sqlite-failure")
    save.save_execution(execution, label="keep", notes="existing projection")
    with sqlite3.connect(store.database_path) as connection:
        connection.executescript(
            """
            CREATE TRIGGER fail_r012_projection_delete
            BEFORE DELETE ON result_artifact_index
            BEGIN
                SELECT RAISE(ABORT, 'injected projection SQLite write failure');
            END;
            """
        )

    with pytest.raises(ExecutionIndexRebuildError) as error:
        persistence.rebuild_index()
    assert isinstance(error.value.__cause__, ResultArtifactIndexError)
    assert isinstance(error.value.__cause__.__cause__, sqlite3.Error)
    loaded = queries.get(execution.result_id)
    assert loaded is not None and loaded.execution == execution


@pytest.mark.parametrize(
    ("injected_error", "expected_error"),
    (
        (ResultArtifactIntegrityError("injected inventory corruption"), ExecutionArtifactIntegrityError),
        (ResultArtifactIndexError("injected inventory SQLite failure"), ExecutionIndexRebuildError),
    ),
)
def test_r012_rebuild_classifies_inventory_store_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    injected_error: Exception,
    expected_error: type[Exception],
) -> None:
    store, persistence, save, _ = _stack(tmp_path)
    save.save_execution(_execution("r012-rebuild-inventory-failure-setup"))

    def fail_inventory() -> Any:
        raise injected_error
        yield  # Keep this a generator so the failure occurs under rebuild's lock.

    monkeypatch.setattr(store, "iter_artifacts", fail_inventory)
    with pytest.raises(expected_error) as error:
        persistence.rebuild_index()
    assert error.value.__cause__ is injected_error


def test_r012_projection_table_rebuild_preserves_metadata_authority(
    tmp_path: Path,
) -> None:
    store, persistence, save, queries = _stack(tmp_path)
    execution = _execution("r012-metadata-preserved-on-rebuild")
    saved = save.save_execution(execution, label="authoritative label", notes="authoritative notes")
    connection = sqlite3.connect(store.database_path)
    try:
        connection.execute("DROP TABLE result_artifact_index")
        connection.commit()
    finally:
        connection.close()

    assert persistence.rebuild_index() == (execution.result_id,)
    loaded = queries.get(execution.result_id)
    assert loaded is not None
    assert (loaded.label, loaded.notes) == ("authoritative label", "authoritative notes")
    assert loaded.persisted_at == saved.persisted_at


def test_r012_whole_database_loss_rebuilds_projection_but_reports_metadata_unknown(
    tmp_path: Path,
) -> None:
    store, persistence, save, queries = _stack(tmp_path)
    execution = _execution("r012-db-loss")
    save.save_execution(execution, label="cannot reconstruct", notes="also lost")
    store.database_path.unlink()

    assert persistence.rebuild_index() == (execution.result_id,)
    loaded = queries.get(execution.result_id)
    assert loaded is not None and loaded.execution == execution
    assert loaded.label is None
    assert loaded.notes is None
    assert loaded.persisted_at is None


def test_r012_metadata_rename_changes_only_metadata_not_artifact_bytes_or_hash(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("r012-rename")
    saved = save.save_execution(execution, label="before", notes="same notes")
    before_bytes = store.read_artifact(execution.result_id)

    save.rename(execution.result_id, "after rename")
    loaded = queries.get(execution.result_id)

    assert loaded is not None
    assert loaded.label == "after rename"
    assert loaded.notes == "same notes"
    assert loaded.payload_hash == saved.payload_hash
    assert store.read_artifact(execution.result_id) == before_bytes


def test_r012_missing_artifact_index_is_never_exposed_and_same_hash_can_repair(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("r012-missing-file")
    save.save_execution(execution)
    artifact_path = store.artifact_root / store.artifact_name_for(execution.result_id)
    artifact_path.unlink()

    with pytest.raises(ExecutionArtifactIntegrityError):
        queries.get(execution.result_id)
    with pytest.raises(ExecutionArtifactIntegrityError):
        queries.list()

    save.save_execution(execution)
    assert queries.get(execution.result_id) is not None


def test_r012_raw_payload_and_identity_hash_mismatches_fail_closed(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("r012-corruption")
    save.save_execution(execution)
    artifact_path = store.artifact_root / store.artifact_name_for(execution.result_id)
    good = artifact_path.read_bytes()
    artifact_path.write_bytes(good + b" ")
    with pytest.raises(ExecutionArtifactIntegrityError):
        queries.get(execution.result_id)

    artifact_path.write_bytes(good)
    connection = sqlite3.connect(store.database_path)
    try:
        connection.execute(
            "UPDATE result_artifact_index SET payload_hash = ? WHERE result_id = ?",
            ("sha256:" + "e" * 64, execution.result_id),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ExecutionArtifactIntegrityError):
        queries.get(execution.result_id)


def test_r012_artifact_id_mismatch_unknown_revision_and_untrusted_index_name_fail_closed(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("r012-wrong-id")
    save.save_execution(execution)
    target = store.artifact_root / store.artifact_name_for(execution.result_id)
    other = encode_execution(_execution("r012-other-id"))
    target.write_bytes(other)
    with pytest.raises(ExecutionArtifactIntegrityError):
        queries.get(execution.result_id)

    target.write_bytes(encode_execution(execution))
    connection = sqlite3.connect(store.database_path)
    try:
        connection.execute(
            "UPDATE result_artifact_index SET artifact_name = ? WHERE result_id = ?",
            ("../../outside.json", execution.result_id),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ExecutionArtifactIntegrityError):
        queries.get(execution.result_id)

    unknown_id = "r012-unknown-revision"
    unknown_path = store.artifact_root / store.artifact_name_for(unknown_id)
    document = _envelope(encode_execution(_execution(unknown_id)))
    document["schema_revision"] = 3
    unknown = _rehash_envelope(document)
    metadata = ArtifactIndexMetadata(
        result_id=unknown_id,
        payload_hash=str(document["payload_hash"]),
        artifact_sha256="sha256:" + hashlib.sha256(unknown).hexdigest(),
        schema_version="recommendation-execution.v1",
        schema_revision=3,
        label="unknown revision",
        notes="",
        persisted_at=datetime.now(timezone.utc).isoformat(),
    )
    store.publish_artifact(unknown, metadata)
    store.index_artifact(metadata)
    with pytest.raises(ExecutionArtifactIntegrityError):
        queries.get(unknown_id)


def test_r012_query_on_empty_root_has_no_filesystem_or_schema_side_effects(
    tmp_path: Path,
) -> None:
    store, _, _, queries = _stack(tmp_path)
    before = set(tmp_path.rglob("*"))
    assert queries.get("no-result") is None
    assert queries.list() == ()
    after = set(tmp_path.rglob("*"))
    assert after == before
    assert not store.database_path.exists()


def test_r012_data_store_module_has_no_app_import() -> None:
    source = Path("data_module/result_artifact_store.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.append(node.module)
    assert all(not name.startswith("app_module") for name in imported_modules)


def test_r012_new_writer_never_calls_legacy_replace_methods(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, save, queries = _stack(tmp_path)

    def fail_legacy(*args: object, **kwargs: object) -> None:
        raise AssertionError("new writer called a legacy repository method")

    monkeypatch.setattr(RecommendationRepository, "save_result", fail_legacy)
    monkeypatch.setattr(RecommendationRepository, "save_result_create_only", fail_legacy)
    execution = _execution("r012-no-legacy-fallback")
    save.save_execution(execution)
    assert queries.get(execution.result_id) is not None
    assert store.read_artifact(execution.result_id) == encode_execution(execution)


def test_r012_legacy_replace_with_same_id_cannot_touch_new_artifact_or_index(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    result_id = "r012-cross-writer-same-id"
    execution = _execution(result_id)
    save.save_execution(execution, label="canonical", notes="immutable bytes")
    before = store.read_artifact(result_id)
    config = _TmpConfig(tmp_path / "output")
    legacy_repository = RecommendationRepository(config)
    legacy = RecommendationResultDTO(
        result_id=result_id,
        result_name="legacy row",
        config={"legacy": True},
        recommendations=[],
        created_at="",
        notes="legacy replace path",
    )

    with pytest.raises(RuntimeError, match="canonical execution namespace"):
        legacy_repository.save_result(legacy, result_name="legacy replace")

    loaded = queries.get(result_id)
    legacy_loaded = legacy_repository.load_result(result_id)
    assert loaded is not None and loaded.execution == execution
    assert loaded.label == "canonical"
    assert store.read_artifact(result_id) == before
    assert legacy_loaded is None
    _under(tmp_path, store.database_path, store.artifact_root / store.artifact_name_for(result_id))


def test_r012_legacy_create_only_with_same_id_cannot_claim_canonical_identity(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    result_id = "r012-cross-writer-create-only"
    execution = _execution(result_id)
    save.save_execution(execution)
    repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    legacy = RecommendationResultDTO(
        result_id=result_id,
        result_name="legacy create-only",
        config={},
        recommendations=[],
        created_at="",
        notes="must be rejected",
    )

    with pytest.raises(RuntimeError, match="canonical execution namespace"):
        repository.save_result_create_only(legacy)
    assert queries.get(result_id) is not None
    assert repository.load_result(result_id) is None
    assert store.read_artifact(result_id) == encode_execution(execution)


def test_r012_existing_legacy_identity_blocks_new_writer_before_artifact(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    result_id = "r012-legacy-first"
    repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    legacy = RecommendationResultDTO(
        result_id=result_id,
        result_name="legacy first",
        config={"legacy": True},
        recommendations=[],
        created_at="2026-09-23T12:00:00+00:00",
        notes="legacy identity",
    )
    repository.save_result(legacy, result_name=legacy.result_name)

    with pytest.raises(ExecutionIdentityConflict):
        save.save_execution(_execution(result_id, score=Decimal("17.00")))

    assert not store.artifact_root.exists()
    loaded = queries.get(result_id)
    assert loaded is not None
    assert loaded.execution is None
    assert loaded.legacy_result is not None
    assert loaded.legacy_result.result_id == result_id
    loaded_legacy = repository.load_result(result_id)
    assert loaded_legacy is not None
    assert loaded_legacy.result_name == "legacy first"


def test_r012_legacy_file_only_orphan_blocks_new_claim_and_remains_recoverable(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    result_id = "r012-legacy-file-only-orphan"
    legacy = RecommendationResultDTO(
        result_id=result_id,
        result_name="legacy orphan",
        config={"legacy": True},
        recommendations=[],
        created_at="2026-09-23T12:00:00+00:00",
        notes="preserve exact legacy bytes",
    )
    repository.save_result_create_only(legacy, result_name=legacy.result_name)
    legacy_path = repository.runs_dir / f"{result_id}.json"
    orphan_bytes = legacy_path.read_bytes()
    with sqlite3.connect(repository.db_path) as connection:
        connection.execute("DELETE FROM runs WHERE result_id = ?", (result_id,))

    assert repository.load_result(result_id) is None
    with pytest.raises(ExecutionIdentityConflict, match="legacy file-only"):
        save.save_execution(_execution(result_id))

    assert legacy_path.read_bytes() == orphan_bytes
    assert tuple(store.artifact_root.glob("*.json")) == ()
    assert store.get_identity_payload_hash(result_id) is None
    assert store.get_index(result_id) is None
    assert queries.get(result_id) is None

    assert repository.save_result_create_only(legacy, result_name=legacy.result_name) == result_id
    assert legacy_path.read_bytes() == orphan_bytes
    assert repository.load_result(result_id) is not None
    loaded = queries.get(result_id)
    assert loaded is not None
    assert loaded.execution is None
    assert loaded.legacy_result is not None
    assert loaded.legacy_result.result_id == result_id


def test_r012_concurrent_legacy_and_canonical_writers_have_one_visible_identity(
    tmp_path: Path,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    result_id = "r012-cross-writer-race"
    execution = _execution(result_id, score=Decimal("23.00"))
    legacy = RecommendationResultDTO(
        result_id=result_id,
        result_name="legacy contender",
        config={"legacy": True},
        recommendations=[],
        created_at="2026-09-23T12:00:00+00:00",
        notes="old namespace contender",
    )
    barrier = Barrier(2)

    def run_canonical() -> str:
        barrier.wait(timeout=10)
        try:
            save.save_execution(execution)
            return "canonical"
        except ExecutionIdentityConflict:
            return "conflict"

    def run_legacy() -> str:
        barrier.wait(timeout=10)
        try:
            repository.save_result(legacy, result_name=legacy.result_name)
            return "legacy"
        except RuntimeError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(lambda fn: fn(), (run_canonical, run_legacy)))

    assert sorted(outcomes).count("conflict") == 1
    assert len(queries.list()) == 1
    visible = queries.get(result_id)
    assert visible is not None
    if "canonical" in outcomes:
        assert visible.execution is not None
        assert repository.load_result(result_id) is None
    else:
        assert visible.execution is None
        assert visible.legacy_result is not None
        assert repository.load_result(result_id) is not None
    _under(tmp_path, store.database_path)


def test_r012_legacy_fixture_reader_is_available_through_unified_read_only_query(
    tmp_path: Path,
) -> None:
    store, _, _, queries = _stack(tmp_path)
    legacy_repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    legacy = RecommendationResultDTO(
        result_id="r012-legacy-fixture",
        result_name="legacy fixture",
        config={"profile": "legacy"},
        recommendations=[
            RecommendationDTO(
                stock_code="2330",
                stock_name="台積電",
                close_price=Decimal("123.40"),
                price_change=1.25,
                total_score=82.5,
                indicator_score=80.0,
                pattern_score=85.0,
                volume_score=82.0,
                recommendation_reasons="legacy fixture",
                industry="半導體",
                regime_match=True,
            )
        ],
        created_at="2026-09-22T12:00:00+00:00",
        notes="copied legacy bytes",
    )
    legacy_repository.save_result(legacy, result_name=legacy.result_name)
    legacy_path = legacy_repository.runs_dir / f"{legacy.result_id}.json"
    before = legacy_path.read_bytes()

    loaded = queries.get(legacy.result_id)
    assert loaded is not None
    assert loaded.execution is None
    assert loaded.legacy_result is not None
    assert loaded.legacy_result.recommendations[0].close_price == Decimal("123.40")
    assert loaded.integrity_basis == "legacy_read_time_hash_only"
    assert loaded.payload_hash is None
    assert loaded.schema_revision is None
    assert loaded.raw_artifact_sha256 == "sha256:" + hashlib.sha256(before).hexdigest()
    assert any(item.result_id == legacy.result_id for item in queries.list())
    assert legacy_path.read_bytes() == before
    assert not store.artifact_root.exists()


def test_r012_root_and_file_symlinks_fail_closed(tmp_path: Path) -> None:
    runs_dir = tmp_path / "output" / "recommendation" / "runs"
    runs_dir.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_root = runs_dir / "execution_artifacts"
    try:
        linked_root.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"host does not permit temporary directory symlinks: {exc}")
    store = ResultArtifactStore(linked_root, runs_dir / "recommendation_runs.db")
    execution = _execution("r012-root-symlink")
    raw = encode_execution(execution)
    payload_hash = str(_envelope(raw)["payload_hash"])
    metadata = ArtifactIndexMetadata(
        result_id=execution.result_id,
        payload_hash=payload_hash,
        artifact_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
        schema_version="recommendation-execution.v1",
        schema_revision=2,
        label="x",
        notes="",
        persisted_at=datetime.now(timezone.utc).isoformat(),
    )
    with pytest.raises(ResultArtifactIntegrityError):
        store.publish_artifact(raw, metadata)
    assert tuple(outside.iterdir()) == ()


def test_r012_symlinked_artifact_is_not_followed(tmp_path: Path) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("r012-file-symlink")
    save.save_execution(execution)
    artifact = store.artifact_root / store.artifact_name_for(execution.result_id)
    artifact.unlink()
    outside = tmp_path / "outside.json"
    outside.write_bytes(encode_execution(execution))
    try:
        artifact.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"host does not permit temporary file symlinks: {exc}")
    with pytest.raises(ExecutionArtifactIntegrityError):
        queries.get(execution.result_id)


@pytest.mark.skipif(os.name != "nt", reason="Windows handle no-follow guard")
def test_r012_windows_artifact_reparse_is_rejected_by_open_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    execution = _execution("r012-win32-handle-no-follow")
    save.save_execution(execution)
    artifact = store.artifact_root / store.artifact_name_for(execution.result_id)
    artifact.unlink()
    outside = tmp_path / "outside.json"
    outside.write_bytes(encode_execution(execution))
    try:
        artifact.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"host does not permit temporary file symlinks: {exc}")

    # Model the check/open race: pathname lstat-based checks miss the link, while
    # CreateFileW(OPEN_REPARSE_POINT) must still reject the opened directory entry.
    monkeypatch.setattr(store, "_is_symlink_or_reparse", lambda _: False)
    with pytest.raises(ExecutionArtifactIntegrityError):
        queries.get(execution.result_id)


@pytest.mark.parametrize("status", (ExecutionStatus.FAILED, ExecutionStatus.CANCELLED))
def test_r012_failed_or_cancelled_execution_is_rejected_before_side_effects(
    tmp_path: Path,
    status: ExecutionStatus,
) -> None:
    store, _, save, queries = _stack(tmp_path)
    base = _execution(f"r012-{status.value}")
    execution = RecommendationExecution(
        result_id=base.result_id,
        request=base.request,
        context=base.context,
        status=status,
        decision=None,
        failure_reason="fixture terminal outcome",
    )
    with pytest.raises(ValueError, match="completed"):
        save.save_execution(execution)
    assert not store.artifact_root.exists()
    assert queries.get(execution.result_id) is None
