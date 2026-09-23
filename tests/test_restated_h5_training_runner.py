from __future__ import annotations

import numpy as np
import pytest

from ml_module.allocation_release_contract import payload_hash
from ml_module.restated_h5_training_runner import (
    _bounded_fit_refs,
    _calibration_ece_bp,
    _collect_training_runtime_binding,
    _model_id,
    _row_id_hash,
    _read_declared_dataset_schema_version,
    _cli_parser,
)


@pytest.mark.parametrize(
    ("probabilities", "targets", "expected"),
    [
        ([0, 10_000], [0, 1], 0),
        ([0, 0], [1, 1], 10_000),
        ([5_000, 5_000], [0, 1], 0),
    ],
)
def test_calibration_ece_bp_exact_examples(
    probabilities: list[int], targets: list[int], expected: int
) -> None:
    assert _calibration_ece_bp(
        np.asarray(probabilities, dtype=np.int64),
        np.asarray(targets, dtype=np.int64),
    ) == expected


def test_row_id_hash_matches_canonical_list_hash_without_materializing_a_list() -> None:
    from types import SimpleNamespace

    ids = ["row:2026-05-20:1256", "row:2026-05-21:1477"]
    rows = SimpleNamespace(
        row_ids=np.asarray([row_id.encode("utf-8") for row_id in ids], dtype="S64")
    )
    assert _row_id_hash(rows, np.asarray([0, 1], dtype=np.int64)) == payload_hash(ids)


def test_h5_fit_defaults_to_all_selected_rows() -> None:
    selected = _bounded_fit_refs(np.arange(235, dtype=np.int64), None)
    assert np.array_equal(selected, np.arange(235, dtype=np.int64))


def test_research_cli_uses_unbounded_h5_fit_by_default() -> None:
    parsed = _cli_parser().parse_args(["--manifest", "m.json", "--output-root", "out"])
    assert parsed.max_fit_rows is None


def test_research_candidate_identity_names_its_linear_algorithm() -> None:
    assert _model_id((5,)) == (
        "baldr-ml-allocation-restated-revision-aware-ridge-logistic-h5-rank-v2"
    )
    assert _model_id((5, 10, 20, 60)) == (
        "baldr-ml-allocation-restated-revision-aware-ridge-logistic-h5-h10-h20-h60-rank-v2"
    )


def test_training_runtime_binding_hashes_sources_versions_and_arguments() -> None:
    binding = _collect_training_runtime_binding(
        invocation_argv=("--manifest", "sealed.json", "--horizons", "5")
    )
    assert binding["source_file_sha256"][
        "ml_module/allocation_out_of_core_training_service.py"
    ].startswith("sha256:")
    assert binding["source_file_sha256"][
        "scripts/train_ml_allocation_restated_research.py"
    ].startswith("sha256:")
    assert {"numpy", "scikit-learn", "scipy", "joblib", "pyarrow", "threadpoolctl"}.issubset(
        binding["software_versions"]
    )
    assert binding["invocation_argv"] == [
        "--manifest",
        "sealed.json",
        "--horizons",
        "5",
    ]


def test_dataset_schema_probe_selects_versioned_identity_builder(tmp_path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        '{"schema_version":"portfolio-ml-restated-research-dataset.v2"}',
        encoding="utf-8",
    )
    assert _read_declared_dataset_schema_version(manifest_path) == (
        "portfolio-ml-restated-research-dataset.v2"
    )
