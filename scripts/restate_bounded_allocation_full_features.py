"""產生 bounded allocation 的 full-prefix restated research dataset。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_module.bounded_allocation_full_feature_restatement import (
    restate_bounded_full_features,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="重算 22,093 列 bounded research dataset 的完整技術特徵"
    )
    parser.add_argument("--original-publication-dir", type=Path, required=True)
    parser.add_argument("--label-restatement-dir", type=Path, required=True)
    parser.add_argument("--source-snapshot-path", type=Path, required=True)
    parser.add_argument("--expected-snapshot-sha256", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--revision-observed-at")
    args = parser.parse_args()
    receipt = restate_bounded_full_features(
        original_publication_dir=args.original_publication_dir,
        label_restatement_dir=args.label_restatement_dir,
        source_snapshot_path=args.source_snapshot_path,
        output_directory=args.output_directory,
        expected_snapshot_sha256=args.expected_snapshot_sha256,
        revision_observed_at=args.revision_observed_at,
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
