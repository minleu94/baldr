from __future__ import annotations

from datetime import date, datetime, time, timezone
import hashlib
import json
from pathlib import Path
import sys
import types
from zoneinfo import ZoneInfo

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from data_module.ml_restatement_current_inputs import _IDENTITY_FIELDS, _payload_hash
from data_module.ml_restatement_research_dataset import (
    LABEL_FIELDS,
    SUPPORTED_HORIZONS,
    arrow_schema,
    expected_feature_contract,
)
from ml_module.restated_h5_training_runner import (
    _close_research_arrays,
    _require_source_custody_for_row_count,
    load_sealed_research_rows,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_AS_OF = "2026-09-23T05:00:00+00:00"


def _sha(letter: str) -> str:
    return "sha256:" + letter * 64


def _row(index: int) -> dict[str, object]:
    names, _scales = expected_feature_contract()
    decision = date(2024, 1, 3 + index)
    stock_event = None if index == 0 else date(2024, 1, 2 + index)
    market_event = date(2024, 1, 2 + index)
    missing = [0] * len(names)
    if stock_event is None:
        missing[21:] = [1] * (len(names) - 21)
    values = [index + 1] * len(names)
    for position, is_missing in enumerate(missing):
        if is_missing:
            values[position] = None
    return {
        "row_id": f"row:{decision.isoformat()}:{1000 + index}",
        "symbol": str(1000 + index),
        "decision_date": decision,
        "decision_at": datetime.combine(decision, time(8, 30), _TAIPEI).isoformat(),
        "local_row_index": index,
        "fold_role": "walk_forward_fit_candidate",
        "fold_ids": ["fixture-fold"],
        "calendar_basis": "observed",
        "stock_event_date": stock_event,
        "market_event_date": market_event,
        "feature_event_asof_at": (
            None
            if stock_event is None
            else datetime.combine(stock_event, time(14, 30), _TAIPEI).isoformat()
        ),
        "feature_available_at": _AS_OF,
        "revision_observed_at": _AS_OF,
        "source_revision_id": "fixture-revision",
        "feature_lineage_hash": _sha("a"),
        "features_scaled_i64": values,
        "feature_missing_mask": missing,
        "target_values_i32": [None] * 6,
        "target_missing_mask": [1] * 6,
        **{
            name: value
            for horizon in SUPPORTED_HORIZONS
            for name, value in (
                (f"label_end_date_h{horizon}", None),
                (f"maturity_at_h{horizon}", None),
                (f"labels_h{horizon}_i64", [None] * len(LABEL_FIELDS)),
                (f"labels_h{horizon}_missing_mask", [1] * len(LABEL_FIELDS)),
                (f"label_basis_h{horizon}", None),
            )
        },
    }


def _write_dataset(root: Path, *, mutation=None) -> tuple[Path, dict[str, object]]:
    import data_module.ml_restatement_research_dataset as dataset_builder

    names, scales = expected_feature_contract()
    partition_dir = root / "year=2024"
    partition_dir.mkdir(parents=True)
    partition_path = partition_dir / "research_dataset.parquet"
    table = pa.Table.from_pylist([_row(index) for index in range(3)], schema=arrow_schema())
    pq.write_table(table, partition_path)
    partition_bytes = partition_path.read_bytes()
    source_hashes = {
        "snapshot_db": {"path": "fixture.db", "sha256": _sha("1")},
        "direct_manifest": {
            "path": "direct.json",
            "file_sha256": _sha("2"),
            "manifest_hash": _sha("3"),
        },
        "discovery_cache": {"path": "discovery.json", "sha256": _sha("4")},
        "corporate_action_manifest": {"path": "actions.json", "sha256": _sha("5")},
        "transfer_receipt": {"path": "receipt.json", "sha256": _sha("6")},
    }
    kernel = {
        "path": "analysis_module/technical_analysis/technical_indicators.py",
        "sha256": _sha("a"),
    }
    builder_hash = _sha("8")
    file_item = {
        "year": 2024,
        "path": "year=2024/research_dataset.parquet",
        "row_count": 3,
        "file_sha256": "sha256:" + hashlib.sha256(partition_bytes).hexdigest(),
        "byte_count": len(partition_bytes),
    }
    manifest: dict[str, object] = {
        "schema_version": "portfolio-ml-restated-research-dataset.v1",
        "source_hashes": source_hashes,
        "feature_ids": list(names),
        "feature_scales": list(scales),
        "feature_order_hash": dataset_builder.canonical_hash(list(zip(names, scales))),
        "kernel": kernel,
        "builder_code_sha256": builder_hash,
        "label_quality_recipe": {"fixture": True},
        "restated_research": True,
        "formal_historical_PIT": False,
        "training_as_of": _AS_OF,
        "revision_observed_at": _AS_OF,
        "row_count": 3,
        "partition_files": [file_item],
        "date_filter": {"start": "2024-01-03", "end": "2024-01-05", "limit_rows": None},
        "symbol_filter": ["1000", "1001", "1002"],
        "feature_count": 62,
        "feature_packs": [{"pack_id": "fixture-all", "feature_ids": list(names)}],
        "feature_registry_hash": _sha("9"),
        "label_fields": list(LABEL_FIELDS),
        "label_scales": [1] * len(LABEL_FIELDS),
        "fold_boundaries": [{"fold_id": "fixture-fold", "test_start": "2024-01-03"}],
        "fold_policy": {
            "purge_trading_days": 60,
            "embargo_trading_days": 5,
            "revision_heldout_start": "2026-05-20",
            "formal_oos": False,
        },
        "source_manifest_hashes": [
            ["sqlite.daily_prices", _sha("1")],
            ["direct.manifest", _sha("2")],
            ["direct.discovery_cache", _sha("4")],
            ["custody.transfer_receipt", _sha("6")],
            ["derived.causal_kernel", _sha("a")],
            ["derived.label_quality_builder", builder_hash],
            ["sidecar.corporate_action_adjustments", _sha("5")],
        ],
        "status": "complete_research_build",
        "research_only": True,
        "promotion_eligible": False,
        "formal_oos": False,
    }
    _seal_identity(manifest)
    manifest_path = root / "manifest.json"
    _write_manifest(manifest_path, manifest)
    return manifest_path, manifest


def _rewrite_partition(manifest_path: Path, manifest: dict[str, object], rows) -> None:
    partition_path = manifest_path.parent / manifest["partition_files"][0]["path"]
    pq.write_table(pa.Table.from_pylist(rows, schema=arrow_schema()), partition_path)
    partition_bytes = partition_path.read_bytes()
    manifest["partition_files"][0]["file_sha256"] = (
        "sha256:" + hashlib.sha256(partition_bytes).hexdigest()
    )
    manifest["partition_files"][0]["byte_count"] = len(partition_bytes)
    _seal_identity(manifest)
    _write_manifest(manifest_path, manifest)


def _seal_identity(manifest: dict[str, object]) -> None:
    identity = _payload_hash({name: manifest[name] for name in _IDENTITY_FIELDS})
    manifest["dataset_identity_hash"] = identity
    manifest["manifest_hash"] = identity
    manifest["dataset_id"] = "ml-restated-research-" + identity[7:31]


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _read_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sidecar(manifest_path: Path, manifest: dict[str, object]) -> dict[str, object]:
    manifest_bytes = manifest_path.read_bytes()
    manifest_hash = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    return {
        "schema_version": "model-repair-source-custody.v1",
        "dataset": {
            "manifest_path": str(manifest_path.resolve()),
            "manifest_file_sha256": manifest_hash,
            "dataset_identity_hash": manifest["dataset_identity_hash"],
            "build_status": "complete_research_build",
            "row_count": manifest["row_count"],
        },
        "job_clocks": {
            "started_at_observed": None,
            "start_source_verification": "not_observed_at_job_start",
            "finished_at": "2026-09-23T05:10:00Z",
            "finished_time_basis": "completion_observed_after_process_exit",
            "end_source_verification_at": "2026-09-23T05:10:01Z",
            "revision_observed_at": _AS_OF,
        },
        "builder": {
            "commit": "7c8a08c2972561410fe357b4cafb67654e97a203",
            "tracked_worktree_clean": True,
            "source_sha256": manifest["builder_code_sha256"],
        },
        "kernel": {
            "commit": "809a75bcb42fa8e58e5b0723a19bba9b5089bd78",
            "tracked_kernel_sources_match_commit": True,
            "manifest_kernel_sha256": manifest["kernel"]["sha256"],
            "audit_events": [
                {
                    "at": "2026-09-23T05:09:00Z",
                    "timing": "after job start; not a start capture",
                    "files": [
                        {
                            "path": "analysis_module/technical_analysis/technical_indicators.py",
                            "sha256_working_bytes": _sha("a"),
                            "sha256_git_blob": _sha("b"),
                            "crlf_normalized_matches_git": True,
                        },
                        {
                            "path": "analysis_module/technical_analysis/indicator_kernels.py",
                            "sha256_working_bytes": _sha("c"),
                            "sha256_git_blob": _sha("d"),
                            "crlf_normalized_matches_git": True,
                        },
                    ],
                },
                {
                    "at": "2026-09-23T05:10:01Z",
                    "timing": "completion source audit",
                    "files": [
                        {
                            "path": "analysis_module/technical_analysis/technical_indicators.py",
                            "sha256_working_bytes": _sha("a"),
                            "sha256_git_blob": _sha("b"),
                            "crlf_normalized_matches_git": True,
                        },
                        {
                            "path": "analysis_module/technical_analysis/indicator_kernels.py",
                            "sha256_working_bytes": _sha("c"),
                            "sha256_git_blob": _sha("d"),
                            "crlf_normalized_matches_git": True,
                        },
                    ],
                },
            ],
        },
        "runtime": {"python": "3.11.9", "numpy": "2.3.5", "pandas": "2.3.3", "talib": "0.6.8"},
        "source_hashes": manifest["source_hashes"],
    }


def _write_sidecar(path: Path, content: dict[str, object]) -> str:
    path.write_text(json.dumps(content, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _v2_sidecar(
    manifest_path: Path,
    manifest: dict[str, object],
    path: Path,
) -> str:
    content = _sidecar(manifest_path, manifest)
    content["dataset_lineage"] = manifest["dataset_lineage"]
    content["patch"] = manifest["patch"]
    content["computation_source_hashes"] = manifest["computation_source_hashes"]
    content["builder"]["source_sha256"] = manifest["builder_code_sha256"]
    content["corrected_subset_builder"] = {
        "commit": "366fd05b5f0711ac22e8d0b806b46c4ef13be087",
        "tracked_worktree_clean": True,
        "source_sha256": manifest["corrected_subset_builder_sha256"],
    }
    computation = manifest["computation_source_hashes"]
    for event in content["kernel"]["audit_events"]:
        event["files"].append(
            {
                "path": "utils/numeric_text.py",
                "sha256_working_bytes": computation["grouped_numeric_parser"],
                "sha256_git_blob": _sha("e"),
                "crlf_normalized_matches_git": True,
            }
        )
    return _write_sidecar(path, content)


def _load(path: Path, tmp_path: Path, **kwargs):
    return load_sealed_research_rows(
        path,
        scratch_root=tmp_path / "scratch",
        observed_as_of=datetime.fromisoformat("2026-09-23T06:00:00+00:00"),
        **kwargs,
    )


_V2_IDENTITY_FIELDS = (
    "schema_version", "source_hashes", "source_manifest_hashes",
    "computation_source_hashes", "feature_count", "feature_ids", "feature_scales",
    "feature_order_hash", "feature_registry_hash", "feature_packs",
    "feature_value_dtype", "feature_missing_mask_semantics", "label_fields",
    "label_scales", "horizons", "horizon_dates_are_independent",
    "label_missing_mask_semantics", "target_fields", "target_missing_mask_semantics",
    "original_row_target_audit", "feature_event_semantics",
    "feature_available_at_semantics", "calendar_basis", "latest_inference_row_policy",
    "fold_policy", "fold_boundaries", "observed_session_dates", "kernel",
    "builder_code_sha256", "corrected_subset_builder_sha256", "label_quality_recipe",
    "restated_research", "formal_historical_PIT", "formal_oos",
    "promotion_eligible", "research_only", "status", "training_as_of",
    "revision_observed_at", "revision", "row_count", "partition_files",
    "date_filter", "symbol_filter", "dataset_lineage", "patch", "dataset_created_at",
)


def _install_v2_identity_module(monkeypatch) -> tuple[str, ...]:
    module_name = "data_module.ml_restatement_research_dataset_v2_merge"
    if module_name not in sys.modules:
        try:
            __import__(module_name)
        except ImportError:
            module = types.ModuleType(module_name)
            module.V2_IDENTITY_FIELDS = _V2_IDENTITY_FIELDS
            module.CORRECTED_SYMBOLS = tuple(f"{1000 + index:04d}" for index in range(22))
            monkeypatch.setitem(sys.modules, module_name, module)
    module = sys.modules[module_name]
    return tuple(module.V2_IDENTITY_FIELDS)


def _seal_v2_identity(manifest: dict[str, object], fields: tuple[str, ...]) -> None:
    identity = _payload_hash(
        {"identity_fields": list(fields), **{name: manifest[name] for name in fields}}
    )
    manifest["dataset_identity_fields"] = list(fields)
    manifest["dataset_identity_hash"] = identity
    manifest["manifest_hash"] = identity
    manifest["dataset_id"] = "ml-restated-research-v2-" + identity[7:31]


def _write_v2_dataset(
    root: Path,
    monkeypatch,
    *,
    mutation: str | None = None,
) -> tuple[Path, dict[str, object]]:
    import data_module.ml_restatement_research_dataset as dataset_builder
    import ml_module.restated_h5_training_runner as runner

    fields = _install_v2_identity_module(monkeypatch)
    v2_module = sys.modules["data_module.ml_restatement_research_dataset_v2_merge"]
    if fields != _V2_IDENTITY_FIELDS:
        raise AssertionError("test fixture identity fields differ from the v2 builder contract")
    names, scales = expected_feature_contract()
    root.mkdir(parents=True, exist_ok=True)
    partition_dir = root / "year=2024"
    partition_dir.mkdir()
    partition_path = partition_dir / "research_dataset.parquet"
    rows = [_row(index) for index in range(3)]
    revision = _sha("0")
    v2_module = sys.modules["data_module.ml_restatement_research_dataset_v2_merge"]
    corrected_symbols = list(v2_module.CORRECTED_SYMBOLS)
    parent_clock = "2026-09-22T04:00:00+00:00"
    for index, row in enumerate(rows):
        if index in (0, 2):
            row["symbol"] = corrected_symbols[index // 2]
            row["row_id"] = f"row:{row['decision_date'].isoformat()}:{row['symbol']}"
            row["feature_available_at"] = _AS_OF
            row["revision_observed_at"] = _AS_OF
        else:
            row["symbol"] = "9999"
            row["row_id"] = f"row:{row['decision_date'].isoformat()}:9999"
            row["feature_available_at"] = parent_clock
            row["revision_observed_at"] = parent_clock
        row["source_revision_id"] = revision
        if index < 2:
            row["target_values_i32"] = [0, 0, 0, 0, 10_000, 0]
            row["target_missing_mask"] = [0] * 6
    if mutation == "non_cash_target":
        rows[0]["target_values_i32"][0] = 1
    pq.write_table(pa.Table.from_pylist(rows, schema=arrow_schema()), partition_path)
    partition_bytes = partition_path.read_bytes()
    source_hashes = {
        "snapshot_db": {"path": "fixture.db", "sha256": revision},
        "direct_manifest": {
            "path": "direct.json",
            "file_sha256": _sha("2"),
            "manifest_hash": _sha("3"),
        },
        "discovery_cache": {"path": "discovery.json", "sha256": _sha("4")},
        "corporate_action_manifest": {"path": "actions.json", "sha256": _sha("5")},
        "transfer_receipt": {"path": "receipt.json", "sha256": _sha("6")},
    }
    builder_hash = _sha("8")
    corrected_builder_hash = _sha("7")
    kernel = {
        "path": "analysis_module/technical_analysis/technical_indicators.py",
        "sha256": _sha("a"),
    }
    computation = {
        "causal_kernel_facade": _sha("a"),
        "causal_kernel_impl": _sha("c"),
        "grouped_numeric_parser": _sha("d"),
        "corrected_subset_builder": corrected_builder_hash,
        "v2_row_merge": builder_hash,
    }
    parent_path, parent_manifest = _write_dataset(root.parent / "parent_v1")
    corrected_path, corrected_manifest = _write_dataset(root.parent / "corrected_subset")
    parent_manifest["training_as_of"] = parent_clock
    parent_manifest["revision_observed_at"] = parent_clock
    _seal_identity(parent_manifest)
    _write_manifest(parent_path, parent_manifest)
    corrected_manifest["row_count"] = 2
    corrected_manifest["symbol_filter"] = corrected_symbols
    _seal_identity(corrected_manifest)
    _write_manifest(corrected_path, corrected_manifest)
    lineage = {
        "parent_v1": {
            "manifest_path": str(parent_path.resolve()),
            "manifest_file_sha256": "sha256:" + hashlib.sha256(parent_path.read_bytes()).hexdigest(),
            "dataset_identity_hash": parent_manifest["dataset_identity_hash"],
            "row_count": 3,
            "revision_observed_at": parent_clock,
        },
        "corrected_subset": {
            "manifest_path": str(corrected_path.resolve()),
            "manifest_file_sha256": "sha256:" + hashlib.sha256(corrected_path.read_bytes()).hexdigest(),
            "dataset_identity_hash": corrected_manifest["dataset_identity_hash"],
            "row_count": 2,
            "symbols": corrected_symbols,
        },
    }
    patch = {
        "join_key": "row_id",
        "replaced_row_count": 2,
        "added_row_count": 0,
        "corrected_subset_appended_row_count": 1,
        "merge_recipe_sha256": builder_hash,
        "verification_summary": {
            "parent_row_ids_preserved": True,
            "parent_targets_exact_for_all_parent_rows": True,
            "appended_targets_missing": True,
            "corrected_subset_row_ids_unique": True,
            "all_subset_rows_joined_or_added": True,
            "unaffected_feature_and_label_columns_exact": True,
            "corrected_scope_22_symbols_all_history_and_appends": True,
            "snapshot_hashes_match": True,
            "parent_rows": 3,
            "final_rows": 3,
            "unaffected_rows": 1,
            "patched_rows": 2,
            "new_appended_rows": 0,
            "duplicate_row_ids": 0,
        },
    }
    source_manifest_hashes = [
        ["sqlite.daily_prices", revision],
        ["direct.manifest", _sha("2")],
        ["direct.discovery_cache", _sha("4")],
        ["custody.transfer_receipt", _sha("6")],
        ["derived.causal_kernel", _sha("a")],
        ["derived.label_quality_builder", corrected_builder_hash],
        ["sidecar.corporate_action_adjustments", _sha("5")],
        ["parent.v1.dataset.manifest", lineage["parent_v1"]["manifest_file_sha256"]],
        ["corrected.symbol.subset.dataset.manifest", lineage["corrected_subset"]["manifest_file_sha256"]],
        ["derived.grouped_numeric_parser", _sha("d")],
        ["derived.v2.row_merge", builder_hash],
        ["derived.causal_kernel.impl", _sha("c")],
    ]
    partition = {
        "year": 2024,
        "path": "year=2024/research_dataset.parquet",
        "row_count": 3,
        "file_sha256": "sha256:" + hashlib.sha256(partition_bytes).hexdigest(),
        "byte_count": len(partition_bytes),
    }
    manifest: dict[str, object] = {
        "schema_version": "portfolio-ml-restated-research-dataset.v2",
        "source_hashes": source_hashes,
        "source_manifest_hashes": source_manifest_hashes,
        "computation_source_hashes": computation,
        "feature_count": 62,
        "feature_ids": list(names),
        "feature_scales": list(scales),
        "feature_order_hash": dataset_builder.canonical_hash(list(zip(names, scales))),
        "feature_registry_hash": _sha("9"),
        "feature_packs": [{"pack_id": "fixture-all", "feature_ids": list(names)}],
        "feature_value_dtype": "nullable int64 fixed-size list[62]; missing values are Arrow null",
        "feature_missing_mask_semantics": "0=observed, 1=missing; null feature value iff mask is 1",
        "label_fields": list(LABEL_FIELDS),
        "label_scales": [1] * len(LABEL_FIELDS),
        "horizons": list(SUPPORTED_HORIZONS),
        "horizon_dates_are_independent": True,
        "label_missing_mask_semantics": "0=observed, 1=missing",
        "target_fields": [
            "target_weight_bp", "delta_weight_bp", "risk_contribution_bp",
            "risky_budget_bp", "cash_bp", "rebalance_worthwhile",
        ],
        "target_missing_mask_semantics": "0=original Direct target present, 1=missing",
        "original_row_target_audit": {
            "artifact": "output/qa/model_repair_review/original_target_values_audit.json",
            "artifact_sha256": runner.TARGET_VALUES_AUDIT_HASH,
            "source_manifest_sha256": runner.TARGET_AUDIT_MANIFEST_HASH,
            "direct_baseline_row_count": 2,
            "target_observed_row_count": 2,
            "target_field_observed_counts": {
                field: 2 for field in (
                    "target_weight_bp", "delta_weight_bp", "risk_contribution_bp",
                    "risky_budget_bp", "cash_bp", "rebalance_worthwhile",
                )
            },
            "appended_targets": "missing; never teacher-filled",
        },
        "feature_event_semantics": "stock/market source events precede decisions",
        "feature_available_at_semantics": "revision verification clock; historical PIT false",
        "calendar_basis": "observed TAIEX sessions",
        "latest_inference_row_policy": "research current row",
        "fold_policy": {
            "purge_trading_days": 60,
            "embargo_trading_days": 5,
            "revision_heldout_start": "2026-05-20",
            "formal_oos": False,
        },
        "fold_boundaries": [{"fold_id": "fixture-fold", "test_start": "2024-01-03"}],
        "observed_session_dates": ["2024-01-02", "2024-01-03", "2024-01-04"],
        "kernel": kernel,
        "builder_code_sha256": builder_hash,
        "corrected_subset_builder_sha256": corrected_builder_hash,
        "label_quality_recipe": {"fixture": True},
        "restated_research": True,
        "formal_historical_PIT": False,
        "formal_oos": False,
        "promotion_eligible": False,
        "research_only": True,
        "status": "complete_research_build",
        "training_as_of": _AS_OF,
        "revision_observed_at": _AS_OF,
        "revision": revision,
        "row_count": 3,
        "partition_files": [partition],
        "date_filter": {"start": "2024-01-03", "end": "2024-01-05", "limit_rows": None},
        "symbol_filter": ["1000", "1001", "1002"],
        "dataset_lineage": lineage,
        "patch": patch,
        "dataset_created_at": "2026-09-23T05:30:00Z",
    }
    if mutation == "wrong_source_alias":
        manifest["source_manifest_hashes"][9][1] = _sha("z")
    _seal_v2_identity(manifest, fields)
    manifest_path = root / "manifest.json"
    _write_manifest(manifest_path, manifest)
    if mutation == "wrong_declared_count":
        manifest["patch"]["verification_summary"]["parent_rows"] = 2
        _seal_v2_identity(manifest, fields)
        _write_manifest(manifest_path, manifest)
    return manifest_path, manifest


def test_loader_validates_full_manifest_and_preserves_nullable_stock_event(tmp_path: Path) -> None:
    manifest_path, _manifest = _write_dataset(tmp_path / "dataset")
    data = _load(manifest_path, tmp_path)
    try:
        assert data.row_count == 3
        assert data.feature_ids == expected_feature_contract()[0]
        assert int(data.event_days[0]) == -1
        assert bytes(data.event_at[0]).rstrip(b"\x00") == b""
        assert np.all(np.asarray(data.label_masks[5][0]) == 1)
    finally:
        _close_research_arrays(data)


@pytest.mark.parametrize("mutation", ["identity", "order", "scale", "status", "row_count"])
def test_loader_rejects_manifest_identity_contract_or_inventory_mutations(
    tmp_path: Path,
    mutation: str,
) -> None:
    manifest_path, manifest = _write_dataset(tmp_path / "dataset")
    changed = _read_manifest(manifest_path)
    if mutation == "identity":
        changed["dataset_identity_hash"] = _sha("f")
    elif mutation == "order":
        changed["feature_ids"][0], changed["feature_ids"][1] = (
            changed["feature_ids"][1],
            changed["feature_ids"][0],
        )
        changed["feature_order_hash"] = _payload_hash(
            list(zip(changed["feature_ids"], changed["feature_scales"]))
        )
        _seal_identity(changed)
    elif mutation == "scale":
        changed["feature_scales"][0] += 1
        changed["feature_order_hash"] = _payload_hash(
            list(zip(changed["feature_ids"], changed["feature_scales"]))
        )
        _seal_identity(changed)
    elif mutation == "status":
        changed["status"] = "building"
    elif mutation == "row_count":
        changed["row_count"] = 4
        _seal_identity(changed)
    _write_manifest(manifest_path, changed)
    with pytest.raises((TypeError, ValueError), match="identity|feature|complete|row_count"):
        _load(manifest_path, tmp_path)


def test_loader_rehashes_partitions_after_materialization(tmp_path: Path, monkeypatch) -> None:
    manifest_path, manifest = _write_dataset(tmp_path / "dataset")
    partition = manifest_path.parent / manifest["partition_files"][0]["path"]
    import ml_module.restated_h5_training_runner as runner

    original = runner._fixed_list_values
    changed = False

    def mutate_after_read(array, row_count, width):
        nonlocal changed
        result = original(array, row_count, width)
        if not changed:
            with partition.open("ab") as stream:
                stream.write(b" ")
            changed = True
        return result

    monkeypatch.setattr(runner, "_fixed_list_values", mutate_after_read)
    with pytest.raises(ValueError, match="byte count mismatch|SHA-256 mismatch"):
        _load(manifest_path, tmp_path)


@pytest.mark.parametrize("mutation", ["stock_feature", "market_feature", "stock_clock"])
def test_loader_rejects_event_clock_and_observed_feature_conflicts(
    tmp_path: Path,
    mutation: str,
) -> None:
    manifest_path, manifest = _write_dataset(tmp_path / "dataset")
    rows = [_row(index) for index in range(3)]
    if mutation == "stock_feature":
        rows[0]["features_scaled_i64"][21] = 1
        rows[0]["feature_missing_mask"][21] = 0
    elif mutation == "market_feature":
        rows[1]["market_event_date"] = None
    elif mutation == "stock_clock":
        rows[1]["feature_event_asof_at"] = None
    _rewrite_partition(manifest_path, manifest, rows)
    message = "stock-only features|market/sector features|stock event date"
    with pytest.raises(ValueError, match=message):
        _load(manifest_path, tmp_path)


def test_external_custody_is_validated_before_and_after_loading(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    manifest_path, manifest = _write_dataset(dataset_root)
    custody_path = tmp_path / "source_custody.json"
    custody_hash = _write_sidecar(custody_path, _sidecar(manifest_path, manifest))
    data = _load(
        manifest_path,
        tmp_path,
        source_custody_path=custody_path,
        source_custody_hash=custody_hash,
    )
    try:
        assert data.source_custody_hash == custody_hash
        content = _sidecar(manifest_path, manifest)
        content["runtime"]["numpy"] = "changed-after-load"
        _write_sidecar(custody_path, content)
        with pytest.raises(RuntimeError, match="sidecar changed"):
            data.verify_source_integrity(phase="fit-complete")
    finally:
        _close_research_arrays(data)


def test_external_custody_rejects_hash_and_manifest_binding_mismatch(tmp_path: Path) -> None:
    manifest_path, manifest = _write_dataset(tmp_path / "dataset")
    custody_path = tmp_path / "source_custody.json"
    content = _sidecar(manifest_path, manifest)
    wrong_binding = dict(content)
    wrong_binding["dataset"] = dict(content["dataset"], dataset_identity_hash=_sha("e"))
    digest = _write_sidecar(custody_path, wrong_binding)
    with pytest.raises(ValueError, match="identity"):
        _load(
            manifest_path,
            tmp_path,
            source_custody_path=custody_path,
            source_custody_hash=digest,
        )
    with pytest.raises(ValueError, match="file SHA-256 mismatch"):
        _load(
            manifest_path,
            tmp_path,
            source_custody_path=custody_path,
            source_custody_hash=_sha("f"),
        )


@pytest.mark.parametrize("clock_mutation", ["invented_start", "end_before_finish"])
def test_external_custody_rejects_inconsistent_observation_clocks(
    tmp_path: Path,
    clock_mutation: str,
) -> None:
    manifest_path, manifest = _write_dataset(tmp_path / "dataset")
    custody_path = tmp_path / "source_custody.json"
    content = _sidecar(manifest_path, manifest)
    if clock_mutation == "invented_start":
        content["job_clocks"]["started_at_observed"] = "2026-09-23T05:00:00Z"
    else:
        content["job_clocks"]["end_source_verification_at"] = "2026-09-23T05:09:59Z"
    digest = _write_sidecar(custody_path, content)
    with pytest.raises(ValueError, match="start capture|completion and observation clocks"):
        _load(
            manifest_path,
            tmp_path,
            source_custody_path=custody_path,
            source_custody_hash=digest,
        )


def test_full_size_dataset_requires_external_source_custody() -> None:
    with pytest.raises(ValueError, match="100000 rows"):
        _require_source_custody_for_row_count(100_001, None)
    _require_source_custody_for_row_count(100_000, None)
    _require_source_custody_for_row_count(100_001, Path("source_custody.json"))


def test_v2_loader_replays_lineage_cash_targets_and_external_source_custody(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import ml_module.restated_h5_training_runner as runner

    monkeypatch.setattr(runner, "ORIGINAL_DIRECT_TARGET_ROW_COUNT", 2)
    monkeypatch.setattr(runner, "CORRECTED_SUBSET_APPENDED_ROW_COUNT", 1)
    manifest_path, manifest = _write_v2_dataset(tmp_path / "dataset", monkeypatch)
    custody_path = tmp_path / "training" / "source_custody.json"
    custody_path.parent.mkdir()
    custody_hash = _v2_sidecar(manifest_path, manifest, custody_path)
    data = _load(
        manifest_path,
        tmp_path,
        source_custody_path=custody_path,
        source_custody_hash=custody_hash,
    )
    try:
        assert data.manifest["schema_version"] == "portfolio-ml-restated-research-dataset.v2"
        assert data.row_count == 3
        assert data.source_custody["patch"] == manifest["patch"]
        assert data.dataset_identity_hash == manifest["dataset_identity_hash"]
    finally:
        _close_research_arrays(data)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("wrong_source_alias", "source_manifest_hashes"),
        ("wrong_declared_count", "verification_summary.parent_rows"),
        ("non_cash_target", "cash-only"),
    ],
)
def test_v2_loader_rejects_mutated_lineage_or_non_cash_original_targets(
    tmp_path: Path,
    monkeypatch,
    mutation: str,
    message: str,
) -> None:
    import ml_module.restated_h5_training_runner as runner

    monkeypatch.setattr(runner, "ORIGINAL_DIRECT_TARGET_ROW_COUNT", 2)
    monkeypatch.setattr(runner, "CORRECTED_SUBSET_APPENDED_ROW_COUNT", 1)
    manifest_path, _manifest = _write_v2_dataset(
        tmp_path / "dataset", monkeypatch, mutation=mutation
    )
    with pytest.raises(ValueError, match=message):
        _load(manifest_path, tmp_path)


def test_v2_loader_rehashes_external_custody_after_materialization(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import ml_module.restated_h5_training_runner as runner

    monkeypatch.setattr(runner, "ORIGINAL_DIRECT_TARGET_ROW_COUNT", 2)
    monkeypatch.setattr(runner, "CORRECTED_SUBSET_APPENDED_ROW_COUNT", 1)
    manifest_path, manifest = _write_v2_dataset(tmp_path / "dataset", monkeypatch)
    custody_path = tmp_path / "training" / "source_custody.json"
    custody_path.parent.mkdir()
    custody_hash = _v2_sidecar(manifest_path, manifest, custody_path)
    original = runner._fixed_list_values
    changed = False

    def mutate_after_read(array, row_count, width):
        nonlocal changed
        result = original(array, row_count, width)
        if not changed:
            with custody_path.open("ab") as stream:
                stream.write(b" ")
            changed = True
        return result

    monkeypatch.setattr(runner, "_fixed_list_values", mutate_after_read)
    with pytest.raises(RuntimeError, match="sidecar changed"):
        _load(
            manifest_path,
            tmp_path,
            source_custody_path=custody_path,
            source_custody_hash=custody_hash,
        )
