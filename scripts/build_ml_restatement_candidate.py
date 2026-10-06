"""由已核驗正式修訂來源建立 candidate-only V3 研究資料集。"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Sequence

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from data_module.ml_restatement_research_candidate_source import write_candidate_source_profile
from data_module.ml_restatement_research_dataset import sha256_file
from data_module.ml_restatement_research_dataset_v3 import OfficialMarketDatasetBuilder


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a candidate-only V3 research dataset from a verified repair source.")
    parser.add_argument("--snapshot-db", type=Path, required=True)
    parser.add_argument("--expected-snapshot-sha256", required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--expected-source-manifest-sha256", required=True)
    parser.add_argument("--official-market-manifest", type=Path, required=True)
    parser.add_argument("--official-market-hash", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--custody-dir", type=Path, required=True)
    parser.add_argument("--symbols", help="Optional comma-separated stock symbols; omit for the full candidate dataset")
    parser.add_argument("--decision-date-start", type=date.fromisoformat)
    parser.add_argument("--decision-date-end", type=date.fromisoformat)
    parser.add_argument("--limit-rows", type=int)
    parser.add_argument("--no-appends", action="store_true")
    args = parser.parse_args(argv)

    profile_path = args.custody_dir.with_name(args.custody_dir.name + ".candidate_source_profile.json")
    profile = write_candidate_source_profile(
        snapshot_db=args.snapshot_db,
        expected_snapshot_sha256=args.expected_snapshot_sha256,
        source_manifest=args.source_manifest,
        expected_source_manifest_sha256=args.expected_source_manifest_sha256,
        official_market_manifest=args.official_market_manifest,
        expected_market_sha256=args.official_market_hash,
        profile_path=profile_path,
    )
    builder = OfficialMarketDatasetBuilder(
        official_market_manifest=profile.market_manifest,
        official_market_hash=profile.market_sha256,
        output_dir=args.output_dir,
        custody_dir=args.custody_dir,
        symbols=tuple(item.strip() for item in args.symbols.split(",") if item.strip()) if args.symbols else (),
        decision_date_start=args.decision_date_start,
        decision_date_end=args.decision_date_end,
        limit_rows=args.limit_rows,
        include_appends=not args.no_appends,
        candidate_source_profile_path=profile.profile_path,
        candidate_source_profile_sha256=profile.profile_file_sha256,
    )
    try:
        manifest_path = builder.build()
        print(json.dumps({
            "manifest_path": str(manifest_path),
            "manifest_file_sha256": sha256_file(manifest_path),
            "candidate_source_profile_path": str(profile.profile_path),
            "candidate_source_profile_sha256": profile.profile_file_sha256,
            "candidate_only": True,
            "historical_pit": False,
        }, ensure_ascii=False), flush=True)
    finally:
        builder.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
