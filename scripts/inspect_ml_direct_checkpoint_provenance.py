"""Read-only Direct checkpoint provenance inspection and recovery planning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.portfolio_ml_direct_numeric_store import (  # noqa: E402
    inspect_direct_checkpoint_provenance,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store-root",
        type=Path,
        required=True,
        help="Direct numeric store root containing runs/<run_id>/checkpoint.json",
    )
    parser.add_argument(
        "--maintenance-output-dir",
        type=Path,
        help=(
            "optional OOC training output dir used to locate the maintenance "
            "lock for read-only custody inspection"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    plan = inspect_direct_checkpoint_provenance(
        args.store_root,
        maintenance_output_dir=args.maintenance_output_dir,
    )
    print(json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
