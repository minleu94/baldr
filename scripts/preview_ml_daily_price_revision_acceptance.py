"""為封存的價格修訂資料產生只讀 research acceptance preview。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.ml_daily_price_revision_acceptance_preview import (  # noqa: E402
    AcceptancePreviewError,
    EXPECTED_TRANSFER_RECEIPT_SHA256,
    build_revision_acceptance_preview,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument(
        "--training-as-of", required=True,
        help="候選訓練時間，必須是含時區的 ISO 8601 timestamp",
    )
    parser.add_argument(
        "--expected-transfer-sha256", default=EXPECTED_TRANSFER_RECEIPT_SHA256,
        help="封存 transfer receipt 的核准 SHA-256",
    )
    args = parser.parse_args(argv)
    try:
        result = build_revision_acceptance_preview(
            archive_root=args.archive_root,
            training_as_of=args.training_as_of,
            expected_transfer_receipt_sha256=args.expected_transfer_sha256,
        )
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
        print(json.dumps({
            "status": "blocked",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "research_only": True,
            "historical_pit_eligible": False,
            "formal_training_allowed": False,
            "formal_oos_allowed": False,
            "promotion_eligible": False,
            "production_alpha_bp": 0,
            "fit_performed": False,
            "model_loaded": False,
        }, ensure_ascii=True, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
