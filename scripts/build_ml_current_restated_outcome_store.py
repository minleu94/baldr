"""從已釘選的 current-restated 年度 raw shards 建立研究 outcome numeric store。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_module.portfolio_ml_current_restated_outcome_store import (  # noqa: E402
    CurrentRestatedOutcomeStoreError,
    CurrentRestatedOutcomeStoreRequest,
    PortfolioMLCurrentRestatedOutcomeStoreBuilder,
)
from data_module.ml_storage_capacity import StorageCapacityError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a bounded current-restated outcome-only research store from "
            "an explicitly pinned annual raw publication."
        )
    )
    parser.add_argument("--raw-publication-manifest", type=Path, required=True)
    parser.add_argument(
        "--expected-raw-publication-manifest-sha256", required=True
    )
    parser.add_argument("--expected-core-dataset-manifest-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--benchmark-entity-id", default="TAIEX")
    parser.add_argument("--target-symbols", nargs="+", required=True)
    parser.add_argument("--minimum-train-dates", type=int, default=125)
    parser.add_argument("--test-date-count", type=int, default=63)
    parser.add_argument("--purge-trading-days", type=int, default=60)
    parser.add_argument("--embargo-trading-days", type=int, default=5)
    parser.add_argument("--max-raw-rows", type=int, default=1_000_000)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root used by the strict research-output boundary.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        request = CurrentRestatedOutcomeStoreRequest(
            raw_publication_manifest_path=args.raw_publication_manifest,
            expected_raw_publication_manifest_sha256=(
                args.expected_raw_publication_manifest_sha256
            ),
            expected_raw_dataset_manifest_sha256=(
                args.expected_core_dataset_manifest_sha256
            ),
            output_root=args.output_dir,
            benchmark_entity_id=args.benchmark_entity_id,
            target_symbols=tuple(args.target_symbols),
            minimum_train_dates=args.minimum_train_dates,
            test_date_count=args.test_date_count,
            purge_trading_days=args.purge_trading_days,
            embargo_trading_days=args.embargo_trading_days,
            max_raw_rows=args.max_raw_rows,
            repository_root=args.repository_root,
        )
        publication = PortfolioMLCurrentRestatedOutcomeStoreBuilder().build(request)
    except (CurrentRestatedOutcomeStoreError, StorageCapacityError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "portfolio-ml-current-restated-outcome-cli.v1",
                    "status": "blocked",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "formal_training_eligible": False,
                    "historical_pit_eligible": False,
                },
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "schema_version": "portfolio-ml-current-restated-outcome-cli.v1",
                "status": "completed_research_only",
                "run_id": publication.run_id,
                "manifest_path": str(publication.manifest_path),
                "latest_manifest_path": str(publication.latest_manifest_path),
                "manifest_sha256": publication.manifest_sha256,
                "raw_publication_manifest_sha256": (
                    publication.raw_publication_manifest_sha256
                ),
                "raw_dataset_manifest_sha256": (
                    publication.raw_dataset_manifest_sha256
                ),
                "feature_registry_sha256": publication.feature_registry_sha256,
                "observation_count": publication.observation_count,
                "feature_count": publication.feature_count,
                "fold_count": publication.fold_count,
                "artifact_available_at": publication.artifact_available_at.isoformat(),
                "current_restated": True,
                "historical_pit_eligible": False,
                "formal_training_eligible": False,
                "full_teacher_qualified": False,
            },
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
