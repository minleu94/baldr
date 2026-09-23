"""將已修正的 22 檔資料列合併至完整且不變的 v1 rowset。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from data_module.ml_restatement_research_dataset_v2_merge import (  # noqa: E402
    merge_v2_dataset,
    sha256_file,
)


def _source_hashes() -> dict[str, str]:
    paths = {
        "causal_kernel_facade": REPOSITORY_ROOT / "analysis_module/technical_analysis/technical_indicators.py",
        "causal_kernel_impl": REPOSITORY_ROOT / "analysis_module/technical_analysis/indicator_kernels.py",
        "grouped_numeric_parser": REPOSITORY_ROOT / "utils/numeric_text.py",
        "corrected_subset_builder": REPOSITORY_ROOT / "data_module/ml_restatement_research_dataset.py",
        "v2_row_merge": REPOSITORY_ROOT / "data_module/ml_restatement_research_dataset_v2_merge.py",
    }
    return {name: sha256_file(path) for name, path in paths.items()}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-manifest", type=Path, required=True)
    parser.add_argument("--subset-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-parent-manifest-sha", required=True)
    parser.add_argument("--expected-subset-manifest-sha", required=True)
    parser.add_argument("--original-target-audit", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=65_536)
    args = parser.parse_args(argv)

    manifest_path = merge_v2_dataset(
        args.parent_manifest,
        args.subset_manifest,
        args.output_dir,
        expected_parent_manifest_sha=args.expected_parent_manifest_sha,
        expected_subset_manifest_sha=args.expected_subset_manifest_sha,
        computation_source_hashes=_source_hashes(),
        original_target_audit_path=args.original_target_audit,
        batch_size=args.batch_size,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    print(json.dumps({
        "manifest_path": str(manifest_path),
        "manifest_file_sha256": sha256_file(manifest_path),
        "dataset_identity_hash": manifest["dataset_identity_hash"],
        "row_count": manifest["row_count"],
        "replaced_row_count": manifest["patch"]["replaced_row_count"],
        "added_row_count": manifest["patch"]["added_row_count"],
        "source_hashes": manifest["computation_source_hashes"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
