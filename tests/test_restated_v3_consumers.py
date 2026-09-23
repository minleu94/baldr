"""官方市場 consumer 需保留來源、時鐘、目標與推論邊界。"""
from copy import deepcopy
import json

import pyarrow.parquet as pq
import pytest

from data_module.ml_restatement_current_inputs import validate_restated_manifest_identity
from data_module.ml_restatement_official_market import file_sha256
from data_module.ml_restatement_research_dataset_v3 import SOURCE_FILES, expected_v3_source_pairs
from ml_module.restated_h5_training_runner import _close_research_arrays, load_sealed_research_rows
from ml_module.restated_research_input_contract import OFFICIAL_MARKET_CONTRACT_HASH, require_compatible_market_sources
from ml_module.restated_v3_source_custody import validate_v3_source_custody, v3_custody_identity
from tests.test_ml_restatement_research_dataset_v3 import _source_manifest, _rehash
from tests.test_restated_h5_training_input_integrity import _write_dataset, _write_manifest, _AS_OF


def _v3_dataset(tmp_path, mutation=None):
    import pyarrow as pa
    from data_module.ml_restatement_research_dataset import arrow_schema

    path, old = _write_dataset(tmp_path / "dataset")
    sources = tmp_path / "official"
    sources.mkdir()
    manifest = _source_manifest(sources)
    source_fields = set(manifest) - {key for key, value in manifest.items() if value is None}
    manifest = {**manifest, **old, **{key: manifest[key] for key in source_fields}}
    manifest["revision_observed_at"] = manifest["training_as_of"] = _AS_OF
    manifest["dataset_created_at"] = _AS_OF
    manifest["target_fields"] = ["target_weight_bp", "delta_weight_bp", "risk_contribution_bp", "risky_budget_bp", "cash_bp", "rebalance_worthwhile"]
    manifest["original_row_target_audit"] = {"appended_targets": "missing"}
    partition = path.parent / old["partition_files"][0]["path"]
    rows = pq.ParquetFile(partition).read().to_pylist()
    for row in rows:
        row["source_revision_id"] = manifest["revision"]
        row["target_values_i32"] = [0, 0, 0, 0, 10000, 0]
        row["target_missing_mask"] = [0] * 6
    if mutation:
        mutation(rows)
    pq.write_table(pa.Table.from_pylist(rows, schema=arrow_schema()), partition)
    manifest["partition_files"][0].update(file_sha256=file_sha256(partition), byte_count=partition.stat().st_size, baseline_row_count=3, appended_row_count=0)
    _rehash(manifest)
    _write_manifest(path, manifest)
    return path, manifest


def test_v3_training_loader_accepts_fixed_abi_and_real_source_binding(tmp_path):
    path, manifest = _v3_dataset(tmp_path)
    assert validate_restated_manifest_identity(manifest) == manifest["dataset_identity_hash"]
    data = load_sealed_research_rows(path, scratch_root=tmp_path / "scratch")
    try:
        assert data.row_count == 3
        assert "official.twse_market" in dict(data.source_manifest_hashes)
    finally:
        _close_research_arrays(data)


@pytest.mark.parametrize("kind", ["revision", "clock", "target", "missing_target"])
def test_v3_loader_rejects_rehashed_row_corruption(tmp_path, kind):
    def mutate(rows):
        if kind == "revision":
            rows[0]["source_revision_id"] = "old-snapshot"
        elif kind == "clock":
            rows[0]["revision_observed_at"] = rows[0]["feature_available_at"] = "2026-09-22T00:00:00+00:00"
        elif kind == "target":
            rows[0]["target_values_i32"][0] = 100
        else:
            rows[0]["target_values_i32"] = [None] * 6
            rows[0]["target_missing_mask"] = [1] * 6
    path, _ = _v3_dataset(tmp_path, mutate)
    with pytest.raises(ValueError):
        load_sealed_research_rows(path, scratch_root=tmp_path / "scratch")


def _custody(tmp_path):
    path, manifest = _v3_dataset(tmp_path)
    code_root = tmp_path / "producer"
    for name, relative in SOURCE_FILES.items():
        source = code_root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# fixture " + name, encoding="utf-8")
        manifest["computation_source_hashes"][name] = file_sha256(source)
    manifest["builder_code_sha256"] = manifest["computation_source_hashes"]["official_market_builder"]
    manifest["kernel"]["sha256"] = manifest["computation_source_hashes"]["causal_kernel_facade"]
    manifest["source_manifest_hashes"] = expected_v3_source_pairs(manifest)
    _rehash(manifest)
    _write_manifest(path, manifest)
    started = "2026-09-23T04:59:00+00:00"
    start = {
        "schema_version": "model-repair-source-start.v1", "historical_pit": False,
        "started_at": started, "source_verified_at": _AS_OF,
        "source_code_root": str(code_root), "computation_source_hashes": manifest["computation_source_hashes"],
        "snapshot_db_sha256": manifest["source_hashes"]["snapshot_db"]["sha256"],
        "official_market_manifest_sha256": manifest["source_hashes"]["official_market_capture"]["file_sha256"],
        "direct_manifest_file_sha256": manifest["source_hashes"]["direct_manifest"]["file_sha256"],
    }
    start_path = tmp_path / "source_start.json"
    _write_manifest(start_path, start)
    payload = {
        "schema_version": "model-repair-source-custody.v2", "historical_pit": False,
        "dataset": {"manifest_path": str(path), "manifest_file_sha256": file_sha256(path),
                    "dataset_identity_hash": manifest["dataset_identity_hash"], "row_count": 3, "build_status": "complete_research_build"},
        "job_clocks": {"started_at_observed": started, "start_source_verified_at": _AS_OF,
                       "revision_observed_at": _AS_OF, "finished_at": "2026-09-23T05:01:00+00:00",
                       "start_source_verification": "observed_before_build", "end_source_verification": "rechecked_before_manifest_publication"},
        "source_start": {"path": str(start_path), "file_sha256": file_sha256(start_path)},
        "source_code_root": str(code_root),
        **{name: deepcopy(manifest[name]) for name in ("source_hashes", "computation_source_hashes", "market_source")},
    }
    return path, manifest, payload


def test_v3_custody_uses_actual_start_proof_and_producer_root(tmp_path):
    path, manifest, payload = _custody(tmp_path)
    validate_v3_source_custody(payload, manifest_path=path, manifest_hash=file_sha256(path), manifest=manifest, row_count=3)
    identity = v3_custody_identity(payload, sidecar_hash="sha256:" + "a" * 64)
    assert identity["job_clocks"]["started_at_observed"] is not None
    assert "builder_commit" not in identity


@pytest.mark.parametrize("kind", ["old_schema", "missing_start", "start_hash", "source_code", "row_count", "end_clock", "clock_backdate", "source_binding"])
def test_v3_custody_rejects_inconsistent_evidence(tmp_path, kind):
    path, manifest, payload = _custody(tmp_path)
    if kind == "old_schema":
        payload["schema_version"] = "model-repair-source-custody.v1"
    elif kind == "missing_start":
        payload.pop("source_start")
    elif kind == "start_hash":
        payload["source_start"]["file_sha256"] = "sha256:" + "0" * 64
    elif kind == "source_code":
        (tmp_path / "producer" / next(iter(SOURCE_FILES.values()))).write_text("changed", encoding="utf-8")
    elif kind == "row_count":
        payload["dataset"]["row_count"] = 2
    elif kind == "end_clock":
        payload["job_clocks"]["finished_at"] = "2026-09-23T04:00:00+00:00"
    elif kind == "clock_backdate":
        payload["job_clocks"]["start_source_verified_at"] = "2026-09-23T04:00:00+00:00"
    else:
        payload["source_hashes"]["snapshot_db"]["sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        validate_v3_source_custody(payload, manifest_path=path, manifest_hash=file_sha256(path), manifest=manifest, row_count=3)


def test_official_model_rejects_old_market_but_allows_new_official_batch():
    training = (("official.twse_market", "sha256:" + "1" * 64),)
    with pytest.raises(ValueError, match="official-market"):
        require_compatible_market_sources(training, (("sqlite.daily_prices", "sha256:" + "2" * 64),))
    require_compatible_market_sources(training, (
        ("official.twse_market", "sha256:" + "3" * 64),
        ("contract.official_twse_market", OFFICIAL_MARKET_CONTRACT_HASH),
    ))
