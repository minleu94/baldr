"""Mature scheduled recommendation captures from the current market source."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.config import TWStockConfig  # noqa: E402
from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider  # noqa: E402
from ml_module.recommendation_natural_outcome_service import (  # noqa: E402
    RecommendationNaturalOutcomeService,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--source-db", type=Path, default=None)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--evaluation-date", default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-rows", type=int, default=1000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    config_kwargs = {}
    if args.data_root is not None:
        config_kwargs["data_root"] = args.data_root
    if args.output_root is not None:
        config_kwargs["output_root"] = args.output_root
    config = TWStockConfig(**config_kwargs)
    source_db = args.source_db or config.db_file
    evaluation_date = (
        date.fromisoformat(str(args.evaluation_date)[:10]).isoformat()
        if args.evaluation_date
        else date.today().isoformat()
    )
    result = RecommendationNaturalOutcomeService(
        MLHistoricalSnapshotProvider(source_db)
    ).build_evidence(
        capture_path=args.capture,
        evaluation_date=evaluation_date,
        output_path=args.output,
        max_rows=args.max_rows,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
