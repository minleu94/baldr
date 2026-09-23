"""以逐列 row_id 替換方式建立完整 v2 restated 資料集。

父版 v1 保持不變。本模組串流讀取各年度 Parquet，只替換修正子集中的 row_id，
並保留未受影響列的順序與 Arrow 值。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping, Sequence

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


V2_SCHEMA_VERSION = "portfolio-ml-restated-research-dataset.v2"
CORRECTED_SYMBOLS = (
    "1519", "1590", "2059", "2327", "2330", "2454", "3008", "3443",
    "3533", "3653", "3661", "4763", "5269", "6409", "6415", "6515",
    "6669", "6719", "6781", "6805", "8454", "910708",
)
V2_IDENTITY_FIELDS = (
    "schema_version",
    "source_hashes",
    "source_manifest_hashes",
    "computation_source_hashes",
    "feature_count",
    "feature_ids",
    "feature_scales",
    "feature_order_hash",
    "feature_registry_hash",
    "feature_packs",
    "feature_value_dtype",
    "feature_missing_mask_semantics",
    "label_fields",
    "label_scales",
    "horizons",
    "horizon_dates_are_independent",
    "label_missing_mask_semantics",
    "target_fields",
    "target_missing_mask_semantics",
    "original_row_target_audit",
    "feature_event_semantics",
    "feature_available_at_semantics",
    "calendar_basis",
    "latest_inference_row_policy",
    "fold_policy",
    "fold_boundaries",
    "observed_session_dates",
    "kernel",
    "builder_code_sha256",
    "corrected_subset_builder_sha256",
    "label_quality_recipe",
    "restated_research",
    "formal_historical_PIT",
    "formal_oos",
    "promotion_eligible",
    "research_only",
    "status",
    "training_as_of",
    "revision_observed_at",
    "revision",
    "row_count",
    "partition_files",
    "date_filter",
    "symbol_filter",
    "dataset_lineage",
    "patch",
    "dataset_created_at",
)

V1_IDENTITY_FIELDS = (
    "schema_version",
    "source_hashes",
    "feature_ids",
    "feature_scales",
    "feature_order_hash",
    "kernel",
    "builder_code_sha256",
    "label_quality_recipe",
    "restated_research",
    "formal_historical_PIT",
    "training_as_of",
    "revision_observed_at",
    "row_count",
    "partition_files",
    "date_filter",
    "symbol_filter",
)

_TARGET_VALUE_COLUMN = "target_values_i32"
_TARGET_MASK_COLUMN = "target_missing_mask"
_ROW_KEY_COLUMN = "row_id"
_SYMBOL_COLUMN = "symbol"


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def build_v2_identity_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    declared = manifest.get("dataset_identity_fields")
    if tuple(declared or ()) != V2_IDENTITY_FIELDS:
        raise ValueError("dataset_identity_fields differs from the fixed v2 allowlist")
    missing = [field for field in V2_IDENTITY_FIELDS if field not in manifest]
    if missing:
        raise ValueError(f"v2 identity fields missing from manifest: {missing}")
    return {
        "identity_fields": list(V2_IDENTITY_FIELDS),
        **{field: manifest[field] for field in V2_IDENTITY_FIELDS},
    }


def compute_v2_identity_hash(manifest: Mapping[str, Any]) -> str:
    return canonical_hash(build_v2_identity_payload(manifest))


def compute_v1_identity_hash(manifest: Mapping[str, Any]) -> str:
    missing = [field for field in V1_IDENTITY_FIELDS if field not in manifest]
    if missing:
        raise ValueError(f"v1 identity fields missing from parent manifest: {missing}")
    return canonical_hash({field: manifest[field] for field in V1_IDENTITY_FIELDS})


def verify_manifest_identity(manifest: Mapping[str, Any], *, version: int) -> None:
    expected_version = (
        "portfolio-ml-restated-research-dataset.v1"
        if version == 1 else V2_SCHEMA_VERSION
    )
    if manifest.get("schema_version") != expected_version:
        raise ValueError(f"expected {expected_version}, got {manifest.get('schema_version')!r}")
    actual = compute_v1_identity_hash(manifest) if version == 1 else compute_v2_identity_hash(manifest)
    if manifest.get("dataset_identity_hash") != actual:
        raise ValueError("dataset_identity_hash does not match canonical identity payload")
    if manifest.get("manifest_hash") != actual:
        raise ValueError("manifest_hash does not match dataset_identity_hash")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"manifest must be a JSON object: {path}")
    return value


def _manifest_path(root: Path, item: Mapping[str, Any]) -> Path:
    relative = Path(str(item["path"]))
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        raise ValueError(f"partition path escapes dataset root: {item['path']}")
    return path


def verify_partition_inventory(root: Path, manifest: Mapping[str, Any]) -> dict[int, Path]:
    files = manifest.get("partition_files")
    if not isinstance(files, list) or not files:
        raise ValueError("manifest partition_files must be a non-empty list")
    by_year: dict[int, Path] = {}
    total_rows = 0
    for item in files:
        year = int(item["year"])
        if year in by_year:
            raise ValueError(f"duplicate year in partition inventory: {year}")
        path = _manifest_path(root, item)
        if not path.is_file():
            raise FileNotFoundError(path)
        if int(item["byte_count"]) != path.stat().st_size:
            raise ValueError(f"partition byte count changed: {path}")
        if str(item["file_sha256"]) != sha256_file(path):
            raise ValueError(f"partition hash changed: {path}")
        parquet = pq.ParquetFile(path)
        if int(item["row_count"]) != parquet.metadata.num_rows:
            raise ValueError(f"partition row count changed: {path}")
        by_year[year] = path
        total_rows += int(item["row_count"])
    if total_rows != int(manifest["row_count"]):
        raise ValueError("partition inventory row count differs from manifest")
    return by_year


def _table_from_manifest(root: Path, manifest: Mapping[str, Any], schema: pa.Schema | None = None) -> pa.Table:
    paths = [
        _manifest_path(root, item)
        for item in sorted(manifest["partition_files"], key=lambda entry: int(entry["year"]))
    ]
    tables = []
    for path in paths:
        # read_table 會從 year=YYYY 父目錄推斷 Hive 欄；直接讀 Parquet 檔可保留原 schema。
        table = pq.ParquetFile(path).read()
        if schema is None:
            schema = table.schema
        elif not table.schema.equals(schema, check_metadata=False):
            raise ValueError(f"Arrow schema mismatch: {path}")
        tables.append(table)
    if not tables:
        raise ValueError("no subset partition files")
    return pa.concat_tables(tables, promote_options="none")


def _column_index(schema: pa.Schema, name: str) -> int:
    index = schema.get_field_index(name)
    if index < 0:
        raise ValueError(f"required column missing: {name}")
    return index


@dataclass(frozen=True)
class PartitionMergeStats:
    parent_rows: int
    replaced_rows: int
    appended_rows: int
    target_rows_checked: int
    target_observed_counts: tuple[int, ...]


def merge_partition_file(
    parent_path: Path,
    subset_indices: Mapping[str, int],
    subset_table: pa.Table,
    output_path: Path,
    *,
    batch_size: int = 65_536,
) -> PartitionMergeStats:
    """替換一個父版分區中的 row_id，未命中列直接保留原始 Arrow batch。"""
    parent = pq.ParquetFile(parent_path)
    schema = parent.schema_arrow
    if not schema.equals(subset_table.schema, check_metadata=False):
        raise ValueError(f"subset and parent parquet schemas differ: {parent_path}")
    row_key_i = _column_index(schema, _ROW_KEY_COLUMN)
    symbol_i = _column_index(schema, _SYMBOL_COLUMN)
    target_values_i = _column_index(schema, _TARGET_VALUE_COLUMN)
    target_mask_i = _column_index(schema, _TARGET_MASK_COLUMN)
    subset_keys = subset_table.column(_ROW_KEY_COLUMN).to_pylist()
    subset_key_to_index = subset_indices
    # Determine which subset rows are already represented by this parent year.
    seen_subset_indices: set[int] = set()
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = pq.ParquetWriter(
        temporary_path,
        schema,
        compression="zstd",
        use_dictionary=True,
        write_statistics=True,
    )
    parent_rows = replaced_rows = target_rows_checked = 0
    target_observed_counts = [0] * 6
    try:
        for batch in parent.iter_batches(batch_size=batch_size):
            target_masks = batch.column(target_mask_i)
            for target_index in range(6):
                observed = pc.equal(pc.list_element(target_masks, target_index), 0)
                observed_count = pc.sum(pc.cast(observed, pa.int64())).as_py()
                target_observed_counts[target_index] += int(observed_count or 0)
            batch_keys = batch.column(row_key_i).to_pylist()
            matched = [subset_key_to_index.get(key) for key in batch_keys]
            is_replacement = [index is not None for index in matched]
            if any(is_replacement):
                parent_values = batch.column(target_values_i).to_pylist()
                parent_masks = batch.column(target_mask_i).to_pylist()
                for row_i, subset_i in enumerate(matched):
                    if subset_i is None:
                        continue
                    if subset_i in seen_subset_indices:
                        raise ValueError(f"subset row matched more than once: {subset_keys[subset_i]}")
                    seen_subset_indices.add(subset_i)
                    target_rows_checked += 1
                    if parent_values[row_i] != subset_table.column(target_values_i)[subset_i].as_py():
                        raise ValueError(f"Direct targets changed for row {batch_keys[row_i]}")
                    if parent_masks[row_i] != subset_table.column(target_mask_i)[subset_i].as_py():
                        raise ValueError(f"Direct target mask changed for row {batch_keys[row_i]}")

                gather_indices = pa.array(
                    [0 if index is None else index for index in matched], type=pa.int64()
                )
                replace_mask = pa.array(is_replacement, type=pa.bool_())
                replacement_batch = pc.take(subset_table, gather_indices)
                columns = [
                    pc.if_else(replace_mask, replacement_batch.column(i), batch.column(i))
                    for i in range(batch.num_columns)
                ]
                output_table = pa.Table.from_arrays(columns, schema=schema)
                writer.write_table(output_table, row_group_size=batch_size)
                replaced_rows += sum(is_replacement)
            else:
                writer.write_batch(batch, row_group_size=batch_size)
            parent_rows += batch.num_rows

        # 本次來源範圍預期只替換既有列。未來若支援子集新增 row_id，必須明確計數，不能靜默丟棄。
        extra_indices = [
            i for i, key in enumerate(subset_keys)
            if i not in seen_subset_indices
            and int(subset_table.column("decision_date")[i].as_py().year)
                == int(parent_path.parent.name.split("=", 1)[1])
        ]
        if extra_indices:
            extra = pc.take(subset_table, pa.array(extra_indices, type=pa.int64()))
            writer.write_table(extra, row_group_size=batch_size)
        writer.close()
        os.replace(temporary_path, output_path)
    except Exception:
        writer.close()
        if temporary_path.exists():
            temporary_path.unlink()
        raise
    return PartitionMergeStats(
        parent_rows=parent_rows,
        replaced_rows=replaced_rows,
        appended_rows=len(extra_indices),
        target_rows_checked=target_rows_checked,
        target_observed_counts=tuple(target_observed_counts),
    )


def _verify_subset_rows(subset: pa.Table, symbols: set[str], expected_revision: str) -> dict[str, int]:
    keys = subset.column(_ROW_KEY_COLUMN).to_pylist()
    if len(keys) != len(set(keys)):
        raise ValueError("corrected subset contains duplicate row_id values")
    row_symbols = subset.column(_SYMBOL_COLUMN).to_pylist()
    if set(row_symbols) - symbols:
        raise ValueError("corrected subset contains a symbol outside symbol_filter")
    revisions = set(subset.column("source_revision_id").to_pylist())
    if revisions != {expected_revision}:
        raise ValueError("corrected subset source_revision_id differs from source snapshot")
    return {key: i for i, key in enumerate(keys)}


def _append_source_aliases(
    source_manifest_hashes: Sequence[Sequence[str]],
    *,
    parent_manifest_sha: str,
    subset_manifest_sha: str,
    parser_sha: str,
    merge_sha: str,
    kernel_impl_sha: str,
    facade_sha: str,
    corrected_builder_sha: str,
) -> list[list[str]]:
    aliases = [list(item) for item in source_manifest_hashes]
    if len(aliases) != 7 or [item[0] for item in aliases] != [
        "sqlite.daily_prices", "direct.manifest", "direct.discovery_cache",
        "custody.transfer_receipt", "derived.causal_kernel",
        "derived.label_quality_builder", "sidecar.corporate_action_adjustments",
    ]:
        raise ValueError("parent source_manifest_hashes do not match the audited seven-alias ABI")
    # The original seven source IDs remain stable. The derived slots point at the
    # corrected recipe; the parent v1 manifest below preserves the prior recipe.
    aliases[4][1] = facade_sha
    aliases[5][1] = corrected_builder_sha
    aliases.extend([
        ["parent.v1.dataset.manifest", parent_manifest_sha],
        ["corrected.symbol.subset.dataset.manifest", subset_manifest_sha],
        ["derived.grouped_numeric_parser", parser_sha],
        ["derived.v2.row_merge", merge_sha],
        ["derived.causal_kernel.impl", kernel_impl_sha],
    ])
    return aliases


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def merge_v2_dataset(
    parent_manifest_path: Path,
    subset_manifest_path: Path,
    output_dir: Path,
    *,
    expected_parent_manifest_sha: str,
    expected_subset_manifest_sha: str,
    computation_source_hashes: Mapping[str, str],
    original_target_audit_path: Path,
    expected_target_baseline_rows: int = 3_353_096,
    batch_size: int = 65_536,
) -> Path:
    """Build a sealed full rowset v2 directory from parent and corrected subset."""
    parent_manifest_path = parent_manifest_path.resolve()
    subset_manifest_path = subset_manifest_path.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing v2 output: {output_dir}")
    stage = output_dir.with_name(output_dir.name + ".staging")
    if stage.exists():
        raise FileExistsError(f"refusing to reuse existing staging directory: {stage}")

    parent_manifest_sha = sha256_file(parent_manifest_path)
    subset_manifest_sha = sha256_file(subset_manifest_path)
    if parent_manifest_sha != expected_parent_manifest_sha:
        raise ValueError("parent manifest SHA differs from the caller's sealed expectation")
    if subset_manifest_sha != expected_subset_manifest_sha:
        raise ValueError("corrected subset manifest SHA differs from the caller's sealed expectation")
    parent = _read_json(parent_manifest_path)
    subset_manifest = _read_json(subset_manifest_path)
    verify_manifest_identity(parent, version=1)
    verify_manifest_identity(subset_manifest, version=1)
    if parent.get("status") != "complete_research_build" or subset_manifest.get("status") != "complete_research_build":
        raise ValueError("both input datasets must have complete_research_build status")
    if parent.get("source_hashes") != subset_manifest.get("source_hashes"):
        raise ValueError("parent and subset source_hashes differ")
    snapshot_sha = parent["source_hashes"]["snapshot_db"]["sha256"]
    if snapshot_sha != subset_manifest["source_hashes"]["snapshot_db"]["sha256"]:
        raise ValueError("parent and subset source revisions differ")
    parent_partitions = verify_partition_inventory(parent_manifest_path.parent, parent)
    subset_partitions = verify_partition_inventory(subset_manifest_path.parent, subset_manifest)

    common_symbols = set(str(value) for value in subset_manifest.get("symbol_filter", []))
    if tuple(sorted(common_symbols)) != CORRECTED_SYMBOLS:
        raise ValueError("corrected subset symbol_filter differs from the fixed 22-symbol repair scope")
    if parent.get("feature_ids") != subset_manifest.get("feature_ids"):
        raise ValueError("parent and subset feature IDs differ")
    if parent.get("feature_scales") != subset_manifest.get("feature_scales"):
        raise ValueError("parent and subset feature scales differ")
    if parent.get("label_fields") != subset_manifest.get("label_fields"):
        raise ValueError("parent and subset label ABI differs")
    if parent.get("target_fields") != subset_manifest.get("target_fields"):
        raise ValueError("parent and subset target ABI differs")

    # Verify every corrected partition has the same Arrow wire schema as the parent.
    any_parent_path = next(iter(parent_partitions.values()))
    parent_schema = pq.ParquetFile(any_parent_path).schema_arrow
    subset_table = _table_from_manifest(subset_manifest_path.parent, subset_manifest, parent_schema)
    subset_indices = _verify_subset_rows(subset_table, common_symbols, snapshot_sha)
    if int(subset_table.num_rows) != int(subset_manifest["row_count"]):
        raise ValueError("corrected subset loaded row count differs from its manifest")

    # 原始 Direct matrix 有 3,353,096 列可觀測 target；子集每個 join row 都要保留父版 target。
    audit = _read_json(original_target_audit_path)
    if int(audit.get("total_rows", -1)) != expected_target_baseline_rows:
        raise ValueError("original Direct target audit row count changed")
    audit_sha = sha256_file(original_target_audit_path)
    target_names = list(parent.get("target_fields", []))
    if len(target_names) != 6:
        raise ValueError("expected six Direct target fields")

    stage.mkdir(parents=True)
    subset_symbols = sorted(common_symbols)
    parent_year_entries = {int(item["year"]): item for item in parent["partition_files"]}
    years = sorted(set(parent_partitions) | set(subset_partitions))
    used_subset: set[int] = set()
    total_replaced = total_added = parent_rows_seen = 0
    target_observed_counts = [0] * len(target_names)
    output_entries: list[dict[str, Any]] = []
    try:
        for year in years:
            out = stage / f"year={year}" / "research_dataset.parquet"
            if year in parent_partitions:
                stats = merge_partition_file(
                    parent_partitions[year], subset_indices, subset_table, out,
                    batch_size=batch_size,
                )
                parent_rows_seen += stats.parent_rows
                total_replaced += stats.replaced_rows
                total_added += stats.appended_rows
                for target_index, observed_count in enumerate(stats.target_observed_counts):
                    target_observed_counts[target_index] += observed_count
                # 重新串流父版 row_id，確認子集每列只在一個年度分區中命中。
                pf = pq.ParquetFile(parent_partitions[year])
                for batch in pf.iter_batches(columns=[_ROW_KEY_COLUMN], batch_size=batch_size):
                    for key in batch.column(0).to_pylist():
                        idx = subset_indices.get(key)
                        if idx is not None:
                            if idx in used_subset:
                                raise ValueError(f"subset row appears in multiple parent partitions: {key}")
                            used_subset.add(idx)
            else:
                # 若未來新增一個父版沒有的年度，依子集原順序與 schema 寫出。
                indices = [
                    i for i, value in enumerate(subset_table.column("decision_date").to_pylist())
                    if value.year == year
                ]
                if not indices:
                    continue
                new_table = pc.take(subset_table, pa.array(indices, type=pa.int64()))
                out.parent.mkdir(parents=True, exist_ok=True)
                pq.write_table(new_table, out, compression="zstd", use_dictionary=True)
                for idx in indices:
                    if idx in used_subset:
                        raise ValueError("corrected subset row appears in more than one partition")
                    used_subset.add(idx)
                total_added += len(indices)
            parquet = pq.ParquetFile(out)
            out_entry = {
                "year": year,
                "path": f"year={year}\\research_dataset.parquet",
                "row_count": parquet.metadata.num_rows,
                "baseline_row_count": int(parent_year_entries.get(year, {}).get("baseline_row_count", 0)),
                "appended_row_count": int(parent_year_entries.get(year, {}).get("appended_row_count", 0)) + int(year not in parent_year_entries) * parquet.metadata.num_rows,
                "file_sha256": sha256_file(out),
                "byte_count": out.stat().st_size,
            }
            output_entries.append(out_entry)

        if used_subset != set(range(subset_table.num_rows)):
            missing_indices = sorted(set(range(subset_table.num_rows)) - used_subset)
            raise ValueError(f"{len(missing_indices)} corrected subset rows did not join to parent or append")
        if total_replaced + total_added != int(subset_table.num_rows):
            raise ValueError("corrected subset replacement/addition counts do not reconcile")
        if total_added != 0:
            raise ValueError(f"expected exact full-rowset replacement; found {total_added} new row IDs")
        if parent_rows_seen != int(parent["row_count"]):
            raise ValueError("parent row count changed during merge")
        if any(count != expected_target_baseline_rows for count in target_observed_counts):
            raise ValueError(
                "parent target_missing_mask counts differ from the audited Direct baseline: "
                f"expected={expected_target_baseline_rows}, actual={target_observed_counts}"
            )
        if sum(item["row_count"] for item in output_entries) != int(parent["row_count"]):
            raise ValueError("v2 row count must equal the complete parent rowset")

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        parser_sha = computation_source_hashes["grouped_numeric_parser"]
        merge_sha = computation_source_hashes["v2_row_merge"]
        facade_sha = computation_source_hashes["causal_kernel_facade"]
        corrected_builder_sha = computation_source_hashes["corrected_subset_builder"]
        kernel_impl_sha = computation_source_hashes["causal_kernel_impl"]
        audit_target_counts = {
            name: target_observed_counts[index]
            for index, name in enumerate(target_names)
        }
        original_audit = dict(parent.get("original_row_target_audit", {}))
        original_audit.update({
            "artifact_sha256": audit_sha,
            "source_manifest_sha256": str(audit["source_manifest_sha256"]),
            "direct_baseline_row_count": expected_target_baseline_rows,
            "target_observed_row_count": expected_target_baseline_rows,
            "target_field_observed_counts": audit_target_counts,
        })
        lineage = {
            "parent_v1": {
                "manifest_path": str(parent_manifest_path),
                "manifest_file_sha256": parent_manifest_sha,
                "dataset_identity_hash": parent["dataset_identity_hash"],
                "row_count": int(parent["row_count"]),
                "revision_observed_at": parent["revision_observed_at"],
            },
            "corrected_subset": {
                "manifest_path": str(subset_manifest_path),
                "manifest_file_sha256": subset_manifest_sha,
                "dataset_identity_hash": subset_manifest["dataset_identity_hash"],
                "row_count": int(subset_manifest["row_count"]),
                "symbols": subset_symbols,
                "revision_observed_at": subset_manifest["revision_observed_at"],
            },
        }
        patch = {
            "join_key": "row_id",
            "symbols": subset_symbols,
            "patch_version": "symbol-row-replace-by-row-id.v1",
            "replaced_row_count": total_replaced,
            "added_row_count": total_added,
            "corrected_subset_baseline_row_count": sum(
                int(item.get("baseline_row_count", item["row_count"]))
                for item in subset_manifest["partition_files"]
            ),
            "corrected_subset_appended_row_count": sum(
                int(item.get("appended_row_count", 0))
                for item in subset_manifest["partition_files"]
            ),
            "verification_summary": {
                "parent_row_ids_preserved": True,
                "parent_targets_exact_for_all_parent_rows": True,
                "appended_targets_missing": True,
                "corrected_subset_row_ids_unique": True,
                "all_subset_rows_joined_or_added": True,
                "unaffected_feature_and_label_columns_exact": True,
                "corrected_scope_22_symbols_all_history_and_appends": True,
                "snapshot_hashes_match": True,
                "parent_rows": int(parent["row_count"]),
                "final_rows": int(parent["row_count"]),
                "unaffected_rows": int(parent["row_count"]) - total_replaced,
                "patched_rows": total_replaced,
                "new_appended_rows": total_added,
                "duplicate_row_ids": 0,
            },
        }
        source_aliases = _append_source_aliases(
            parent["source_manifest_hashes"],
            parent_manifest_sha=parent_manifest_sha,
            subset_manifest_sha=subset_manifest_sha,
            parser_sha=parser_sha,
            merge_sha=merge_sha,
            kernel_impl_sha=kernel_impl_sha,
            facade_sha=facade_sha,
            corrected_builder_sha=corrected_builder_sha,
        )
        merged = {
            **parent,
            "schema_version": V2_SCHEMA_VERSION,
            "revision": snapshot_sha,
            "source_hashes": dict(parent["source_hashes"]),
            "source_manifest_hashes": source_aliases,
            "computation_source_hashes": {
                key: str(value) for key, value in computation_source_hashes.items()
            },
            "kernel": dict(subset_manifest["kernel"]),
            "builder_code_sha256": merge_sha,
            "corrected_subset_builder_sha256": corrected_builder_sha,
            "label_quality_recipe": dict(subset_manifest["label_quality_recipe"]),
            "original_row_target_audit": original_audit,
            "row_count": int(parent["row_count"]),
            "partition_files": output_entries,
            "symbol_filter": [],
            "dataset_lineage": lineage,
            "patch": patch,
            "dataset_created_at": now,
            "training_as_of": subset_manifest["training_as_of"],
            "revision_observed_at": subset_manifest["revision_observed_at"],
            "restated_research": True,
            "formal_historical_PIT": False,
            "formal_oos": False,
            "promotion_eligible": False,
            "research_only": True,
            "status": "complete_research_build",
            "dataset_identity_fields": list(V2_IDENTITY_FIELDS),
        }
        merged["dataset_identity_hash"] = compute_v2_identity_hash(merged)
        merged["manifest_hash"] = merged["dataset_identity_hash"]
        merged["dataset_id"] = "ml-restated-research-v2-" + merged["dataset_identity_hash"].split(":", 1)[1][:24]
        _write_json_atomic(stage / "manifest.json", merged)
        verify_manifest_identity(merged, version=2)
        stage.rename(output_dir)
    except Exception:
        # 保留失敗的 staging 產物供診斷，不覆寫或遞迴刪除可能有用的證據。
        raise
    return output_dir / "manifest.json"
