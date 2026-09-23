"""為凍結的 bounded 資料集建立研究用途的標籤重述。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_module.bounded_allocation_label_restatement import (
    restate_bounded_training_publication,
)


SNAPSHOT_SHA256 = (
    "sha256:38ab1d1dfd201285ed817c8e94f689f91a50b39dc30cdbb8a90a49b7ce898771"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "重算跨越 2026-05-20 價格修正日的成熟標籤，不更動 bounded row ID、特徵、targets 或 state。"
        )
    )
    parser.add_argument("--source-publication", required=True, type=Path)
    parser.add_argument("--source-snapshot", required=True, type=Path)
    parser.add_argument("--repair-receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--expected-snapshot-sha256",
        default=SNAPSHOT_SHA256,
        help="唯讀封存 SQLite 來源快照的預期 SHA-256。",
    )
    parser.add_argument(
        "--revision-observed-at",
        help="重建實際可用時間的 ISO timestamp；預設使用當下 UTC 時間。",
    )
    args = parser.parse_args()
    result = restate_bounded_training_publication(
        source_publication_dir=args.source_publication,
        source_snapshot_path=args.source_snapshot,
        repair_receipt_path=args.repair_receipt,
        output_directory=args.output,
        expected_snapshot_sha256=args.expected_snapshot_sha256,
        revision_observed_at=args.revision_observed_at,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
