from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import data_module.ml_restatement_current_capture as capture_module
from data_module.ml_restatement_current_inputs import prepare_restated_current_inputs
from data_module.ml_restatement_research_dataset import sha256_file
from data_module.ml_restatement_research_dataset_v2_merge import (
    CORRECTED_SYMBOLS, V2_IDENTITY_FIELDS, compute_v2_identity_hash,
)
from tests.test_ml_restatement_current_inputs import _CAPTURE, _HASH, _fixture_dataset
from tests.test_ml_restatement_current_capture import _Clock, _sources


def _write_identity(path, manifest):
    fingerprint = compute_v2_identity_hash(manifest)
    manifest.update(dataset_id="ml-restated-research-v2-" + fingerprint[7:31],
                    dataset_identity_hash=fingerprint, manifest_hash=fingerprint)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return sha256_file(path)


def _v2_fixture(root: Path):
    path, _ = _fixture_dataset(root)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    old_clock = manifest["revision_observed_at"]
    new_clock = "2026-09-23T12:10:00+08:00"
    parquet_path = root / "research.parquet"
    table = pq.ParquetFile(parquet_path).read()
    rows = table.to_pylist()
    rows[1].update(symbol="2330", row_id="row:2026-09-23:2330",
                   revision_observed_at=new_clock, feature_available_at=new_clock)
    for row in rows:
        row["source_revision_id"] = _HASH
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), parquet_path)
    manifest["partition_files"][0].update(file_sha256=sha256_file(parquet_path), byte_count=parquet_path.stat().st_size)
    for name in V2_IDENTITY_FIELDS:
        manifest.setdefault(name, None)
    comp = {name: _HASH for name in ("grouped_numeric_parser", "v2_row_merge", "causal_kernel_impl",
                                    "causal_kernel_facade", "corrected_subset_builder")}
    aliases = ["sqlite.daily_prices", "direct.manifest", "direct.discovery_cache", "custody.transfer_receipt",
               "derived.causal_kernel", "derived.label_quality_builder", "sidecar.corporate_action_adjustments",
               "parent.v1.dataset.manifest", "corrected.symbol.subset.dataset.manifest", "derived.grouped_numeric_parser",
               "derived.v2.row_merge", "derived.causal_kernel.impl"]
    manifest.update(
        schema_version="portfolio-ml-restated-research-dataset.v2", dataset_identity_fields=list(V2_IDENTITY_FIELDS),
        source_hashes={"snapshot_db": {"sha256": _HASH}}, source_manifest_hashes=[[name, _HASH] for name in aliases],
        computation_source_hashes=comp, builder_code_sha256=_HASH, corrected_subset_builder_sha256=_HASH,
        revision=_HASH, revision_observed_at=new_clock, training_as_of=new_clock,
        dataset_created_at="2026-09-23T12:20:00+08:00", formal_oos=False,
        dataset_lineage={
            "parent_v1": {"manifest_file_sha256": _HASH, "row_count": 2, "revision_observed_at": old_clock},
            "corrected_subset": {"manifest_file_sha256": _HASH, "row_count": 1, "revision_observed_at": new_clock,
                                 "symbols": list(CORRECTED_SYMBOLS)},
        },
        patch={"symbols": list(CORRECTED_SYMBOLS), "join_key": "row_id", "added_row_count": 0,
               "patch_version": "symbol-row-replace-by-row-id.v1", "replaced_row_count": 1},
    )
    return path, _write_identity(path, manifest)


def test_current_v2_retains_each_actual_parent_or_subset_revision(tmp_path):
    manifest, fingerprint = _v2_fixture(tmp_path / "v2")
    prepared = prepare_restated_current_inputs(
        manifest_path=manifest, expected_manifest_file_hash=fingerprint,
        symbols=("1256", "2330"), captured_at=_CAPTURE,
    )
    available = {row.symbol: row.features[0].available_at for row in prepared.rows}
    assert available == {"1256": "2026-09-23T12:00:00+08:00", "2330": "2026-09-23T12:10:00+08:00"}
    assert prepared.binding.dataset_id.startswith("ml-restated-research-v2-")


@pytest.mark.parametrize("failure", ["row_clock", "source_alias", "lineage_clock", "future_creation", "field_allowlist"])
def test_current_v2_rejects_self_consistent_invalid_lineage(tmp_path, failure):
    path, _ = _v2_fixture(tmp_path / "v2")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if failure == "row_clock":
        parquet = path.parent / "research.parquet"
        table = pq.ParquetFile(parquet).read()
        rows = table.to_pylist()
        rows[1]["revision_observed_at"] = "2026-09-23T12:00:00+08:00"
        pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), parquet)
        manifest["partition_files"][0].update(file_sha256=sha256_file(parquet), byte_count=parquet.stat().st_size)
    elif failure == "source_alias":
        manifest["source_manifest_hashes"][-1][1] = "sha256:" + "b" * 64
    elif failure == "lineage_clock":
        manifest["dataset_lineage"]["parent_v1"]["revision_observed_at"] = "2026-09-23T12:11:00+08:00"
    elif failure == "future_creation":
        manifest["dataset_created_at"] = "2026-09-23T14:00:00+08:00"
    if failure == "field_allowlist":
        manifest["dataset_identity_fields"].pop()
        path.write_text(json.dumps(manifest), encoding="utf-8")
        fingerprint = sha256_file(path)
    else:
        fingerprint = _write_identity(path, manifest)
    with pytest.raises(ValueError):
        prepare_restated_current_inputs(
            manifest_path=path, expected_manifest_file_hash=fingerprint,
            symbols=("1256", "2330"), captured_at=_CAPTURE,
        )


def test_new_capture_from_v2_uses_own_prefix_identity_and_drops_merge_claims(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_module, "datetime", _Clock)
    template, fingerprint = _v2_fixture(tmp_path / "template")
    source_root = tmp_path / "source"
    source_root.mkdir()
    database, receipt = _sources(source_root)
    manifest, current_hash = capture_module.capture_restated_current_dataset(
        database_path=database, template_manifest_path=template,
        expected_template_manifest_hash=fingerprint, price_repair_receipt=receipt,
        expected_price_receipt_hash=sha256_file(receipt), symbols=("1256",), output_root=tmp_path / "capture",
    )
    result = json.loads(manifest.read_text(encoding="utf-8"))
    assert result["schema_version"] == "portfolio-ml-restated-research-dataset.v1"
    assert not {"patch", "dataset_lineage", "dataset_identity_fields", "computation_source_hashes"} & result.keys()
    assert result["source_hashes"]["template_manifest"]["sha256"] == fingerprint
    prepared = prepare_restated_current_inputs(
        manifest_path=manifest, expected_manifest_file_hash=current_hash, symbols=("1256",), captured_at=_CAPTURE,
    )
    assert prepared.rows[0].targets is None
    assert prepared.binding.dataset_id != json.loads(template.read_text(encoding="utf-8"))["dataset_id"]
