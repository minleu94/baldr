"""C1 U4 canonical/legacy query readiness，僅使用合成資料與 tmp_path。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
from typing import Mapping

import pytest

from app_module.dtos import RecommendationResultDTO
from app_module.recommendation.codec import (
    ExecutionCodecError,
    decode_execution_envelope,
    encode_execution,
)
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
from app_module.recommendation.persistence import (
    ExecutionArtifactIntegrityError,
    RecommendationExecutionPersistence,
)
from app_module.recommendation.queries import (
    LegacyRecommendationBytes,
    RecommendationExecutionQueries,
    SQLiteLegacyRecommendationRawByteReader,
)
from data_module.contracts.market import SourceRef
from data_module.result_artifact_store import (
    ArtifactIndexMetadata,
    ResultArtifactStore,
)
from decision_module.recommendation.contracts import (
    DecisionBatch,
    RecommendationItem,
    UniverseReference,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "c1_consumer_readiness"


def _fixture_manifest() -> dict[str, dict[str, object]]:
    manifest = json.loads(
        (FIXTURE_ROOT / "fixture_manifest.json").read_text(encoding="utf-8")
    )
    result = {}
    for entry in manifest["entries"]:
        raw = (FIXTURE_ROOT / entry["file"]).read_bytes()
        assert len(raw) == entry["byte_length"]
        assert "sha256:" + hashlib.sha256(raw).hexdigest() == entry["sha256"]
        result[entry["fixture_id"]] = entry
    return result


def _stack(tmp_path: Path) -> tuple[ResultArtifactStore, RecommendationExecutionPersistence, RecommendationExecutionQueries]:
    runs_dir = tmp_path / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)
    return store, persistence, RecommendationExecutionQueries(persistence)


def _install_legacy_row(
    runs_dir: Path,
    *,
    fixture_name: str = "r016_legacy_run_zh.json",
    result_id: str = "c1-r016-legacy",
    stored_path: Path | None = None,
) -> tuple[Path, bytes]:
    runs_dir.mkdir(parents=True, exist_ok=True)
    raw = (FIXTURE_ROOT / fixture_name).read_bytes()
    data_path = runs_dir / f"{result_id}.json"
    data_path.write_bytes(raw)
    database_path = runs_dir / "recommendation_runs.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE runs (
                result_id TEXT PRIMARY KEY,
                result_name TEXT NOT NULL,
                regime TEXT,
                stock_count INTEGER,
                config TEXT,
                notes TEXT,
                created_at TEXT,
                data_path TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO runs
            (result_id, result_name, regime, stock_count, config, notes, created_at, data_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result_id,
                "synthetic legacy name",
                "Trend",
                1,
                "{}",
                "synthetic legacy notes",
                "2026-09-22T12:00:00+00:00",
                str(stored_path or data_path),
            ),
        )
    return data_path, raw


def _artifact_metadata(raw: bytes, *, label: str, notes: str) -> ArtifactIndexMetadata:
    envelope = decode_execution_envelope(raw)
    return ArtifactIndexMetadata(
        result_id=envelope.execution.result_id,
        payload_hash=envelope.payload_hash,
        artifact_sha256=envelope.raw_payload_sha256,
        schema_version=envelope.schema_version,
        schema_revision=envelope.schema_revision,
        label=label,
        notes=notes,
        persisted_at="2026-09-23T00:00:00+00:00",
    )


def test_c1_read_seam_reads_rev1_rev2_without_reencoding_and_rebuild_keeps_source_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixtures = _fixture_manifest()
    for fixture_id, expected_revision in (
        ("r016_execution_rev1", 1),
        ("r016_execution_rev2", 2),
    ):
        case_root = tmp_path / fixture_id
        store, persistence, queries = _stack(case_root)
        fixture = fixtures[fixture_id]
        raw = (FIXTURE_ROOT / str(fixture["file"])).read_bytes()
        envelope = decode_execution_envelope(raw)
        assert envelope.schema_revision == expected_revision
        metadata = _artifact_metadata(raw, label=fixture_id, notes="synthetic")
        store.publish_artifact(raw, metadata)

        # rebuild index 必須把 artifact header 原 revision 寫回 projection。
        assert persistence.rebuild_index() == (envelope.execution.result_id,)
        indexed = store.get_index(envelope.execution.result_id)
        assert indexed is not None
        assert indexed.metadata.schema_revision == expected_revision

        def fail_if_reencoded(*_args: object, **_kwargs: object) -> bytes:
            raise AssertionError("historical query must not call the current writer")

        monkeypatch.setattr("app_module.recommendation.persistence.encode_execution", fail_if_reencoded)
        loaded = queries.get(envelope.execution.result_id)
        assert loaded is not None
        assert loaded.execution == envelope.execution
        assert loaded.schema_version == envelope.schema_version
        assert loaded.schema_revision == expected_revision
        assert loaded.payload_hash == envelope.payload_hash
        assert loaded.raw_artifact_sha256 == envelope.raw_payload_sha256
        assert loaded.integrity_basis == "canonical_payload_and_index_verified"
        assert (store.artifact_root / store.artifact_name_for(envelope.execution.result_id)).read_bytes() == raw
        monkeypatch.undo()


def test_c1_canonical_index_revision_mismatch_fails_closed(tmp_path: Path) -> None:
    store, _, queries = _stack(tmp_path)
    raw = (FIXTURE_ROOT / "r016_execution_rev1.json").read_bytes()
    metadata = replace(
        _artifact_metadata(raw, label="mismatch", notes=""),
        schema_revision=2,
    )
    store.publish_artifact(raw, metadata)
    store.index_artifact(metadata)

    with pytest.raises(ExecutionArtifactIntegrityError, match="hash/schema 不符"):
        queries.get(metadata.result_id)


def test_c1_legacy_sqlite_raw_read_uses_only_read_time_hash_by_default(
    tmp_path: Path,
) -> None:
    fixtures = _fixture_manifest()
    store, _, queries = _stack(tmp_path)
    runs_dir = store.database_path.parent
    raw_path, raw_before = _install_legacy_row(runs_dir)
    tables_before: tuple[str, ...]
    with sqlite3.connect(store.database_path) as connection:
        tables_before = tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        )

    loaded = queries.get("c1-r016-legacy")

    assert loaded is not None
    assert loaded.execution is None
    assert loaded.legacy_result is not None
    assert loaded.legacy_result.result_id == "c1-r016-legacy"
    assert loaded.legacy_result.recommendations[0].stock_code == "2330"
    assert loaded.schema_version is None
    assert loaded.schema_revision is None
    assert loaded.payload_hash is None
    assert loaded.raw_artifact_sha256 == fixtures["r016_legacy_run_zh"]["sha256"]
    assert loaded.integrity_basis == "legacy_read_time_hash_only"
    assert raw_path.read_bytes() == raw_before
    assert any(item.result_id == "c1-r016-legacy" for item in queries.list())
    with sqlite3.connect(store.database_path) as connection:
        tables_after = tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        )
    assert tables_after == tables_before == ("runs",)
    assert not store.artifact_root.exists()


def test_c1_legacy_trusted_expected_hash_is_explicit_and_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    fixtures = _fixture_manifest()
    store, persistence, _ = _stack(tmp_path)
    runs_dir = store.database_path.parent
    raw_path, raw = _install_legacy_row(runs_dir)
    expected = str(fixtures["r016_legacy_run_zh"]["sha256"])
    trusted_reader = SQLiteLegacyRecommendationRawByteReader(
        runs_dir,
        store.database_path,
        trusted_expected_hashes={"c1-r016-legacy": expected},
    )
    trusted_query = RecommendationExecutionQueries(persistence, trusted_reader)
    trusted = trusted_query.get("c1-r016-legacy")
    assert trusted is not None
    assert trusted.integrity_basis == "legacy_trusted_hash_verified"
    assert trusted.raw_artifact_sha256 == expected

    mismatched_reader = SQLiteLegacyRecommendationRawByteReader(
        runs_dir,
        store.database_path,
        trusted_expected_hashes={"c1-r016-legacy": "sha256:" + "0" * 64},
    )
    mismatched_query = RecommendationExecutionQueries(persistence, mismatched_reader)
    with pytest.raises(ExecutionArtifactIntegrityError, match="獨立可信 expected hash"):
        mismatched_query.get("c1-r016-legacy")
    assert raw_path.read_bytes() == raw


def test_c1_legacy_path_scope_and_unified_identity_conflicts_fail_closed(
    tmp_path: Path,
) -> None:
    store, _, queries = _stack(tmp_path)
    runs_dir = store.database_path.parent
    outside = tmp_path / "outside.json"
    outside.write_bytes((FIXTURE_ROOT / "r016_legacy_run_zh.json").read_bytes())
    _install_legacy_row(runs_dir, stored_path=outside)
    with pytest.raises(ExecutionArtifactIntegrityError, match="超出 runs 目錄範圍"):
        queries.get("c1-r016-legacy")

    # 同 ID 同時被兩個 namespace 使用屬完整性衝突；不得挑一方回傳。
    duplicate_root = tmp_path / "duplicate"
    store2, _, queries2 = _stack(duplicate_root)
    execution_raw = (FIXTURE_ROOT / "r016_execution_rev2.json").read_bytes()
    execution = decode_execution_envelope(execution_raw).execution
    metadata = _artifact_metadata(execution_raw, label="canonical", notes="")
    store2.publish_artifact(execution_raw, metadata)
    store2.index_artifact(metadata)
    legacy_path = store2.database_path.parent / f"{execution.result_id}.json"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_bytes(
        json.dumps(
            {
                "result_id": execution.result_id,
                "result_name": "duplicate legacy",
                "config": {},
                "recommendations": [],
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    with sqlite3.connect(store2.database_path) as connection:
        connection.execute(
            "CREATE TABLE runs (result_id TEXT PRIMARY KEY, result_name TEXT, notes TEXT, created_at TEXT, data_path TEXT)"
        )
        connection.execute(
            "INSERT INTO runs (result_id, result_name, notes, created_at, data_path) VALUES (?, ?, ?, ?, ?)",
            (execution.result_id, "duplicate legacy", "", None, str(legacy_path)),
        )
    with pytest.raises(ExecutionArtifactIntegrityError, match="同時出現在"):
        queries2.get(execution.result_id)
    with pytest.raises(ExecutionArtifactIntegrityError, match="重複 result_id"):
        queries2.list()

    artifact_path = store2.artifact_root / store2.artifact_name_for(execution.result_id)
    artifact_path.write_bytes(execution_raw + b" ")
    with pytest.raises(ExecutionArtifactIntegrityError):
        queries2.get(execution.result_id)

    # A canonical artifact without an index is still a canonical identity claim;
    # it must not be hidden by a legacy row with the same result_id.
    orphan_root = tmp_path / "orphan"
    orphan_store, _, orphan_queries = _stack(orphan_root)
    orphan_raw = (FIXTURE_ROOT / "r016_execution_rev2.json").read_bytes()
    orphan_execution = decode_execution_envelope(orphan_raw).execution
    orphan_metadata = _artifact_metadata(orphan_raw, label="orphan", notes="")
    orphan_store.publish_artifact(orphan_raw, orphan_metadata)
    orphan_runs = orphan_store.database_path.parent
    orphan_path = orphan_runs / f"{orphan_execution.result_id}.json"
    orphan_path.write_text(
        json.dumps(
            {
                "result_id": orphan_execution.result_id,
                "result_name": "legacy collision",
                "config": {},
                "recommendations": [],
            }
        ),
        encoding="utf-8",
    )
    with sqlite3.connect(orphan_store.database_path) as connection:
        connection.execute(
            "CREATE TABLE runs (result_id TEXT PRIMARY KEY, result_name TEXT, notes TEXT, created_at TEXT, data_path TEXT)"
        )
        connection.execute(
            "INSERT INTO runs (result_id, result_name, notes, created_at, data_path) VALUES (?, ?, ?, ?, ?)",
            (orphan_execution.result_id, "legacy collision", "", None, str(orphan_path)),
        )
    with pytest.raises(ExecutionArtifactIntegrityError, match="index 缺失.*拒絕 fallback"):
        orphan_queries.get(orphan_execution.result_id)


def test_c1_legacy_query_fails_closed_on_canonical_metadata_only_claim(
    tmp_path: Path,
) -> None:
    store, _, queries = _stack(tmp_path)
    runs_dir = store.database_path.parent
    _install_legacy_row(runs_dir)
    assert store._ensure_schema(create=True)
    canonical_claim = "sha256:" + "a" * 64
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            INSERT INTO result_artifact_metadata
                (result_id, payload_hash, label, notes, persisted_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("c1-r016-legacy", canonical_claim, "", "", None),
        )

    assert store.get_index("c1-r016-legacy") is None
    assert store.get_identity_payload_hash("c1-r016-legacy") == canonical_claim
    assert store.read_artifact("c1-r016-legacy") is None
    with pytest.raises(ExecutionArtifactIntegrityError, match="metadata claim 存在"):
        queries.get("c1-r016-legacy")
    with pytest.raises(ExecutionArtifactIntegrityError, match="metadata claim 存在"):
        queries.list()


def test_c1_legacy_query_fails_closed_when_canonical_metadata_lookup_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, queries = _stack(tmp_path)
    _install_legacy_row(store.database_path.parent)

    def fail_metadata_read(_result_id: str) -> None:
        raise sqlite3.OperationalError("injected metadata lookup failure")

    monkeypatch.setattr(store, "get_identity_payload_hash", fail_metadata_read)
    with pytest.raises(ExecutionArtifactIntegrityError, match="無法讀取 canonical identity metadata"):
        queries.get("c1-r016-legacy")
    with pytest.raises(ExecutionArtifactIntegrityError, match="無法讀取 canonical identity metadata"):
        queries.list()


def test_c1_legacy_get_rejects_duplicate_rows_without_unique_database_constraint(
    tmp_path: Path,
) -> None:
    store, _, queries = _stack(tmp_path)
    runs_dir = store.database_path.parent
    runs_dir.mkdir(parents=True, exist_ok=True)
    legacy_path = runs_dir / "c1-r016-legacy.json"
    legacy_path.write_bytes((FIXTURE_ROOT / "r016_legacy_run_zh.json").read_bytes())
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            CREATE TABLE runs (
                result_id TEXT,
                result_name TEXT,
                notes TEXT,
                created_at TEXT,
                data_path TEXT
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO runs (result_id, result_name, notes, created_at, data_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                ("c1-r016-legacy", "duplicate A", "", None, str(legacy_path)),
                ("c1-r016-legacy", "duplicate B", "", None, str(legacy_path)),
            ),
        )

    with pytest.raises(ExecutionArtifactIntegrityError, match="legacy runs 含重複 result_id"):
        queries.get("c1-r016-legacy")


def test_c1_legacy_reader_rejects_symlinked_result_file(tmp_path: Path) -> None:
    store, _, queries = _stack(tmp_path)
    runs_dir = store.database_path.parent
    legacy_path, _ = _install_legacy_row(runs_dir)
    outside = tmp_path / "outside-legacy.json"
    outside.write_bytes(legacy_path.read_bytes())
    legacy_path.unlink()
    try:
        legacy_path.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"目前 Windows 環境不允許建立測試 symlink: {exc}")

    with pytest.raises(ExecutionArtifactIntegrityError, match="symlink"):
        queries.get("c1-r016-legacy")


def _load_training_fixture_builder():
    source = Path(__file__).with_name("test_recommendation_training_lineage.py")
    spec = importlib.util.spec_from_file_location("c1_u4_training_fixture_builder", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("無法載入既有 synthetic receipt fixture builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._build_verified_training_fixture


def _ml_ready_execution(tmp_path: Path) -> tuple[RecommendationExecution, str]:
    from ml_module.recommendation_inference_provenance import (
        build_inference_projection_receipt,
        persist_inference_projection_receipt,
        validate_provenance_compatibility,
    )
    from ml_module.recommendation_probability_transform import PROBABILITY_TRANSFORM_ID

    learning_root = tmp_path / "learning"
    training, inference, cost_hash = _load_training_fixture_builder()(learning_root)
    candidate_id = "candidate-provenance-1"
    compatibility = validate_provenance_compatibility(
        training,
        inference,
        expected_cost_scenario_hash=cost_hash,
        expected_probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    receipt = build_inference_projection_receipt(
        decision_date="2025-05-01",
        result_id="c1-ml-result",
        candidate_identity={"candidate_id": candidate_id},
        training_provenance=training,
        inference_provenance=inference,
        compatibility=compatibility,
        projections=(
            {
                "stock_code": "1101",
                "status": "active_candidate",
                "model_version": candidate_id,
                "ranking_score_bp": 7_300,
                "ranking_percentile_bp": 8_200,
                "cost_scenario_hash": cost_hash,
            },
            {
                "stock_code": "2330",
                "status": "active_candidate",
                "model_version": candidate_id,
                "ranking_score_bp": 7_200,
                "ranking_percentile_bp": 8_100,
                "cost_scenario_hash": cost_hash,
            },
        ),
    )
    receipt_path = persist_inference_projection_receipt(learning_root, receipt)
    row_hash = str(receipt.payload["projection_rows_sha256"])
    as_of = date(2025, 5, 1)
    item_2330 = RecommendationItem(
        stock_code="2330",
        rule_score=Decimal("82.5000"),
        rank=0,
        universe_ref=UniverseReference(
            policy_id="synthetic-listed-v1",
            snapshot_id="synthetic-members-2025-05-01",
            as_of_date=as_of,
            members_hash="synthetic-members-hash",
        ),
        reasons=("synthetic saved execution",),
    )
    item_1101 = replace(item_2330, stock_code="1101")
    binding = MLReceiptBinding(
        receipt_ref=VersionReference(ReferenceKind.ML_RECEIPT, str(receipt_path)),
        receipt_hash=receipt.receipt_hash,
        result_id="c1-ml-result",
        decision_date=as_of,
        model_candidate_id=candidate_id,
        projected_stock_codes=("1101", "2330"),
        cost_scenario_hash=cost_hash,
    )
    execution = RecommendationExecution(
        result_id="c1-ml-result",
        request=Request(as_of_date=as_of),
        context=Context(
            as_of_date=as_of,
            decision_at=datetime(2025, 5, 1, 12, tzinfo=timezone.utc),
            source_refs=(SourceRef("synthetic-source", revision=1, snapshot_id="synthetic-v1"),),
        ),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=(item_1101, item_2330), regime="Trend"),
        ml_availability=MLAvailability(status=MLAvailabilityStatus.AVAILABLE),
        ml_projection_refs=(VersionReference(ReferenceKind.ML_PROJECTION, row_hash),),
        ml_receipt_refs=(binding,),
    )
    return execution, row_hash


def test_c1_ml_read_view_uses_only_verified_saved_receipt_projection_rows(
    tmp_path: Path,
) -> None:
    _, persistence, queries = _stack(tmp_path)
    execution, row_hash = _ml_ready_execution(tmp_path)
    persistence.save(execution)

    loaded = queries.get(execution.result_id)

    assert loaded is not None
    assert loaded.execution == execution
    assert loaded.ml_read_status == "verified"
    assert len(loaded.ml_projection_rows) == 2
    assert tuple(row["stock_code"] for row in loaded.ml_projection_rows) == ("1101", "2330")
    assert loaded.ml_projection_rows[0]["cost_scenario_hash"] == execution.ml_receipt_refs[0].cost_scenario_hash
    assert execution.ml_projection_refs[0].reference_id == row_hash
    with pytest.raises(TypeError):
        loaded.ml_projection_rows[0]["stock_code"] = "1101"  # type: ignore[index]


@pytest.mark.parametrize("mismatch", ("receipt_hash", "candidate", "cost", "row_hash", "stock_order"))
def test_c1_bound_ml_receipt_mismatch_is_explicitly_unavailable(
    tmp_path: Path,
    mismatch: str,
) -> None:
    _, persistence, queries = _stack(tmp_path)
    execution, _ = _ml_ready_execution(tmp_path)
    binding = execution.ml_receipt_refs[0]
    changes: dict[str, object] = {}
    if mismatch == "receipt_hash":
        changes["receipt_hash"] = "sha256:" + "0" * 64
    elif mismatch == "candidate":
        changes["model_candidate_id"] = "different-candidate"
    elif mismatch == "cost":
        changes["cost_scenario_hash"] = "sha256:" + "f" * 64
    elif mismatch == "stock_order":
        changes["projected_stock_codes"] = ("2330", "1101")
    bad_binding = replace(binding, **changes)
    bad_execution = replace(execution, ml_receipt_refs=(bad_binding,))
    if mismatch == "row_hash":
        bad_execution = replace(
            bad_execution,
            ml_projection_refs=(
                VersionReference(ReferenceKind.ML_PROJECTION, "sha256:" + "e" * 64),
            ),
        )
    persistence.save(bad_execution)

    loaded = queries.get(bad_execution.result_id)

    assert loaded is not None
    assert loaded.execution == bad_execution
    assert loaded.ml_read_status == "unavailable"
    assert loaded.ml_projection_rows == ()
    assert loaded.diagnostics
    assert loaded.diagnostics[0].startswith("ml_receipt_validation_failed:")


def test_c1_duplicate_receipt_row_hash_binding_is_unavailable_without_duplicate_rows(
    tmp_path: Path,
) -> None:
    _, persistence, queries = _stack(tmp_path)
    execution, _ = _ml_ready_execution(tmp_path)
    binding = execution.ml_receipt_refs[0]
    original_path = Path(binding.receipt_ref.reference_id)
    duplicate_dir = original_path.parent / "duplicate-copy"
    duplicate_dir.mkdir()
    duplicate_path = duplicate_dir / original_path.name
    duplicate_path.write_bytes(original_path.read_bytes())
    duplicate_binding = replace(
        binding,
        receipt_ref=VersionReference(ReferenceKind.ML_RECEIPT, str(duplicate_path)),
    )
    duplicated_execution = replace(
        execution,
        ml_receipt_refs=(binding, duplicate_binding),
    )
    persistence.save(duplicated_execution)

    loaded = queries.get(duplicated_execution.result_id)

    assert loaded is not None
    assert loaded.execution == duplicated_execution
    assert loaded.ml_read_status == "unavailable"
    assert loaded.ml_projection_rows == ()
    assert loaded.diagnostics
    assert loaded.diagnostics[0].startswith("ml_receipt_validation_failed:")


def test_c1_ml_unknown_without_receipt_stays_distinct_from_invalid_binding(
    tmp_path: Path,
) -> None:
    store, persistence, queries = _stack(tmp_path)
    raw = (FIXTURE_ROOT / "r016_execution_rev1.json").read_bytes()
    execution = decode_execution_envelope(raw).execution
    metadata = _artifact_metadata(raw, label="unknown ML", notes="synthetic")
    store.publish_artifact(raw, metadata)
    store.index_artifact(metadata)
    loaded = queries.get(execution.result_id)
    assert loaded is not None
    assert loaded.ml_read_status == "unknown"
    assert loaded.ml_projection_rows == ()

    # 未保存的 legacy ML 欄只能透過 legacy DTO readback，不會觸發目前模型載入。
    runs_dir = tmp_path / "legacy" / "recommendation" / "runs"
    _install_legacy_row(runs_dir)
    explicit_legacy = SQLiteLegacyRecommendationRawByteReader(
        runs_dir, runs_dir / "recommendation_runs.db"
    )
    legacy_query = RecommendationExecutionQueries(persistence, explicit_legacy)
    legacy = legacy_query.get("c1-r016-legacy")
    assert legacy is not None
    assert legacy.ml_read_status == "legacy_saved_fields"


def test_c1_legacy_bytes_change_during_read_fails_closed(tmp_path: Path) -> None:
    store, persistence, _ = _stack(tmp_path)
    raw = (FIXTURE_ROOT / "r016_legacy_run_zh.json").read_bytes()
    changed = raw + b" "
    path = str(tmp_path / "legacy.json")
    before = LegacyRecommendationBytes(
        result_id="c1-r016-legacy",
        data_path=path,
        raw_payload=raw,
        label="legacy",
        notes="",
        created_at="2026-09-22T12:00:00+00:00",
        trusted_expected_sha256=None,
    )
    after = replace(before, raw_payload=changed)

    class _ChangingReader:
        def __init__(self) -> None:
            self._calls = 0

        def get(self, result_id: str) -> LegacyRecommendationBytes | None:
            assert result_id == before.result_id
            self._calls += 1
            return before if self._calls == 1 else after

        def list_result_ids(self) -> tuple[str, ...]:
            return (before.result_id,)

    query = RecommendationExecutionQueries(persistence, _ChangingReader())  # type: ignore[arg-type]
    with pytest.raises(ExecutionArtifactIntegrityError, match="bytes/path.*改變"):
        query.get(before.result_id)
    assert not store.artifact_root.exists()
