"""Preview or copy verified official price custody into an isolated candidate root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.ml_prospective_daily_price_capture import (
    capture_prospective_daily_price_candidate,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate existing TWSE/TPEx official custody bytes and optionally copy "
            "them into an isolated, research-only prospective candidate root."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--preview-only",
        action="store_true",
        help="validate sources and report exact hashes/times without writing files",
    )
    mode.add_argument(
        "--capture-candidate",
        action="store_true",
        help="create a bounded, append-only repository candidate; never writes the source DB",
    )
    parser.add_argument("--source-output-root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--source-date", required=True, help="source date as YYYY-MM-DD")
    parser.add_argument(
        "--candidate-root",
        type=Path,
        required=True,
        help="isolated repository output root, outside the source data/database roots",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = capture_prospective_daily_price_candidate(
            source_output_root=args.source_output_root,
            database_path=args.database,
            source_date=args.source_date,
            candidate_root=args.candidate_root,
            preview_only=args.preview_only,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "rejected",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                ensure_ascii=True,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
