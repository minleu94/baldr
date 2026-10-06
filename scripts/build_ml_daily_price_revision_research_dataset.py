"""建立唯讀 late-obtained 研究來源快照；不開啟正式 PIT 或訓練 gate。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.ml_daily_price_revision_research_dataset import (  # noqa: E402
    ResearchDatasetError,
    build_revision_aware_research_dataset,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-snapshot", type=Path, required=True)
    parser.add_argument("--price-pending", type=Path, required=True)
    parser.add_argument("--price-receipt", type=Path, required=True)
    parser.add_argument("--technical-pending", type=Path, required=True)
    parser.add_argument("--technical-receipt", type=Path, required=True)
    parser.add_argument("--technical-backup", type=Path, required=True)
    parser.add_argument("--dryrun-manifest", type=Path, required=True)
    parser.add_argument("--recovery-receipt", type=Path, required=True)
    parser.add_argument("--technical-verification", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--observed-at", type=str)
    args = parser.parse_args(argv)
    try:
        result = build_revision_aware_research_dataset(
            database_path=args.database_snapshot,
            pending_receipt_path=args.price_pending,
            final_receipt_path=args.price_receipt,
            technical_pending_path=args.technical_pending,
            technical_receipt_path=args.technical_receipt,
            technical_backup_path=args.technical_backup,
            dryrun_manifest_path=args.dryrun_manifest,
            recovery_receipt_path=args.recovery_receipt,
            technical_verification_path=args.technical_verification,
            output_root=args.output_root,
            observed_at=args.observed_at,
        )
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
        print(json.dumps({
            "status": "blocked", "error_type": type(exc).__name__,
            "message": str(exc), "evidence": getattr(exc, "evidence", {}),
            "research_only": True, "formal_training_allowed": False,
            "formal_oos_allowed": False, "promotion_eligible": False,
        }, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({
        "status": "accepted_research_source_snapshot", **{
            key: str(value) if isinstance(value, Path) else value
            for key, value in result.items()
        },
        "model_training_input_compatible": False,
        "formal_training_allowed": False, "formal_oos_allowed": False,
        "promotion_eligible": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
