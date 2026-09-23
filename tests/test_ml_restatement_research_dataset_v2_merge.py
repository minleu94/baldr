from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from data_module.ml_restatement_research_dataset_v2_merge import (
    V2_IDENTITY_FIELDS,
    _verify_subset_rows,
    build_v2_identity_payload,
    compute_v2_identity_hash,
    merge_partition_file,
    sha256_file,
    _table_from_manifest,
)


SNAPSHOT = "sha256:" + "a" * 64
SCHEMA = pa.schema([
    pa.field("row_id", pa.string(), nullable=False),
    pa.field("symbol", pa.string(), nullable=False),
    pa.field("decision_date", pa.date32(), nullable=False),
    pa.field("source_revision_id", pa.string(), nullable=False),
    pa.field("target_values_i32", pa.list_(pa.int32(), 6), nullable=False),
    pa.field("target_missing_mask", pa.list_(pa.uint8(), 6), nullable=False),
    pa.field("feature", pa.int64(), nullable=False),
])


def _table(rows: list[dict[str, object]]) -> pa.Table:
    return pa.Table.from_pylist(rows, schema=SCHEMA)


def _row(
    row_id: str,
    symbol: str,
    feature: int,
    *,
    target: int = 0,
    target_mask: int = 0,
) -> dict[str, object]:
    from datetime import date

    return {
        "row_id": row_id,
        "symbol": symbol,
        "decision_date": date(2026, 5, 20),
        "source_revision_id": SNAPSHOT,
        "target_values_i32": [target] * 6,
        "target_missing_mask": [target_mask] * 6,
        "feature": feature,
    }


def test_identity_payload_requires_exact_fixed_allowlist() -> None:
    manifest = {field: {"field": field} for field in V2_IDENTITY_FIELDS}
    manifest["dataset_identity_fields"] = list(V2_IDENTITY_FIELDS)
    payload = build_v2_identity_payload(manifest)
    before = compute_v2_identity_hash(manifest)
    manifest["dataset_identity_fields"] = list(reversed(V2_IDENTITY_FIELDS))
    with pytest.raises(ValueError, match="fixed v2 allowlist"):
        build_v2_identity_payload(manifest)
    manifest["dataset_identity_fields"] = list(V2_IDENTITY_FIELDS)
    manifest["patch"] = {"changed": True}
    assert compute_v2_identity_hash(manifest) != before
    assert payload["identity_fields"] == list(V2_IDENTITY_FIELDS)


def test_merge_partition_replaces_matching_row_and_keeps_parent_order(tmp_path: Path) -> None:
    parent_path = tmp_path / "year=2026" / "research_dataset.parquet"
    parent_path.parent.mkdir()
    parent = _table([_row("row:a", "2330", 11), _row("row:b", "2317", 22)])
    subset = _table([_row("row:a", "2330", 99)])
    pq.write_table(parent, parent_path)
    indices = {"row:a": 0}

    output_path = tmp_path / "out" / "year=2026" / "research_dataset.parquet"
    stats = merge_partition_file(parent_path, indices, subset, output_path, batch_size=1)
    result = pq.read_table(output_path)

    assert result.column("row_id").to_pylist() == ["row:a", "row:b"]
    assert result.column("feature").to_pylist() == [99, 22]
    assert result.column("target_values_i32").to_pylist() == [[0] * 6, [0] * 6]
    assert stats.parent_rows == 2
    assert stats.replaced_rows == 1
    assert stats.appended_rows == 0
    assert stats.target_rows_checked == 1


def test_merge_partition_rejects_changed_original_targets(tmp_path: Path) -> None:
    parent_path = tmp_path / "year=2026" / "research_dataset.parquet"
    parent_path.parent.mkdir()
    pq.write_table(_table([_row("row:a", "2330", 11, target=1)]), parent_path)
    subset = _table([_row("row:a", "2330", 99, target=2)])
    with pytest.raises(ValueError, match="Direct targets changed"):
        merge_partition_file(
            parent_path, {"row:a": 0}, subset,
            tmp_path / "out" / "year=2026" / "research_dataset.parquet",
        )


def test_subset_row_key_must_be_unique_and_revision_must_match() -> None:
    duplicate = _table([_row("row:a", "2330", 1), _row("row:a", "2330", 2)])
    with pytest.raises(ValueError, match="duplicate row_id"):
        _verify_subset_rows(duplicate, {"2330"}, SNAPSHOT)
    wrong_revision = _table([_row("row:a", "2330", 1)])
    with pytest.raises(ValueError, match="source_revision_id"):
        _verify_subset_rows(wrong_revision, {"2330"}, "sha256:" + "b" * 64)


def test_manifest_reader_does_not_infer_hive_year_column(tmp_path: Path) -> None:
    partition = tmp_path / "year=2026" / "research_dataset.parquet"
    partition.parent.mkdir()
    pq.write_table(_table([_row("row:a", "2330", 11)]), partition)
    manifest = {
        "row_count": 1,
        "partition_files": [{
            "year": 2026,
            "path": "year=2026\\research_dataset.parquet",
            "row_count": 1,
            "byte_count": partition.stat().st_size,
            "file_sha256": sha256_file(partition),
        }],
    }

    result = _table_from_manifest(tmp_path, manifest, SCHEMA)

    assert result.schema.names == SCHEMA.names
    assert result.column("row_id").to_pylist() == ["row:a"]
