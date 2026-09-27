from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from ml_module import allocation_release_loader
from ml_module.allocation_release_contract import payload_hash
from ml_module.restated_h5_training_runner import (
    _bounded_fit_refs,
    _calibration_ece_bp,
    _collect_training_runtime_binding,
    _model_id,
    _row_id_hash,
    _read_declared_dataset_schema_version,
    _cli_parser,
    train_and_publish,
)


ROOT = Path(__file__).resolve().parents[1]


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


def test_research_cli_bootstraps_verified_loader_before_runner_help() -> None:
    script = ROOT / "scripts" / "train_ml_allocation_restated_research.py"
    probe = f"""
import runpy
import sys
script = {str(script)!r}
sys.argv = [script, "--help"]
try:
    runpy.run_path(script, run_name="__main__")
except SystemExit as exc:
    assert exc.code == 0
from app_module import allocation_release_adapter as adapter
from ml_module import allocation_release_loader as loader
assert loader._registered_loader is adapter.load_allocation_release
assert loader._registered_output_type is adapter.LoadedAllocationRelease
"""
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
        env={**os.environ, "PYTHONUTF8": "1"},
    )

    assert completed.returncode == 0, completed.stderr


def test_runner_cold_import_does_not_register_application_loader() -> None:
    probe = """
import sys
from ml_module import allocation_release_loader as loader
import ml_module.restated_h5_training_runner
assert loader._registered_loader is None
assert loader._registered_output_type is None
assert "app_module.allocation_release_adapter" not in sys.modules
assert "scripts.build_ml_allocation_post_freeze_feature_repair" not in sys.modules
assert "scripts.infer_ml_allocation_copilot" not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_programmatic_training_fails_before_output_creation_without_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "release-output"
    monkeypatch.setattr(allocation_release_loader, "_registered_loader", None)
    monkeypatch.setattr(allocation_release_loader, "_registered_output_type", None)

    with pytest.raises(RuntimeError, match="bootstrap the application release adapter"):
        train_and_publish(
            manifest_path=tmp_path / "does-not-exist.json",
            output_root=output_root,
        )

    assert not output_root.exists()


def test_module_cli_fails_before_output_creation_without_bootstrap(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "module-cli-output"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ml_module.restated_h5_training_runner",
            "--manifest",
            str(tmp_path / "missing-manifest.json"),
            "--output-root",
            str(output_root),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )

    assert completed.returncode != 0
    assert "bootstrap the application release adapter" in completed.stderr
    assert not output_root.exists()


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
