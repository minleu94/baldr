"""只擷取官方上市／上櫃當日估值資料並保存原始回執；不寫正式資料庫。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.current_official_valuation import capture_current_official_valuation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        required=True,
        type=Path,
        help="保存官方原始回應與雜湊回執的目錄；不會存取或修改正式 SQLite。",
    )
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--wrapper-run-id")
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")

    result = capture_current_official_valuation(
        args.output_root.absolute(),
        wrapper_run_id=args.wrapper_run_id,
        timeout_seconds=args.timeout_seconds,
    )
    payload = {
        "schema_version": "official-current-valuation-run.v1",
        "status": result.status,
        "run_id": result.run_id,
        "wrapper_run_id": result.wrapper_run_id,
        "receipt_path": str(result.receipt_path),
        "receipt_sha256": result.receipt_sha256,
        "completed_at": result.completed_at.isoformat(),
        "formal_pit_eligible": result.formal_pit_eligible,
        "historical_pit_eligible": False,
        "markets": [
            {
                "market": item.market,
                "status": item.status,
                "source_date": item.source_date.isoformat() if item.source_date else None,
                "available_at": item.available_at.isoformat() if item.available_at else None,
                "source_row_count": item.source_row_count,
                "unique_stock_count": item.unique_stock_count,
                "numeric_counts": dict(item.numeric_counts),
                "missing_counts": dict(item.missing_counts),
                "receipt_path": str(item.receipt_path) if item.receipt_path else None,
                "receipt_sha256": item.receipt_sha256,
                "raw_response_path": str(item.raw_response_path) if item.raw_response_path else None,
                "raw_response_sha256": item.raw_response_sha256,
                "raw_response_bytes": item.raw_response_bytes,
                "failure_receipt_path": str(item.failure_receipt_path) if item.failure_receipt_path else None,
                "failure_receipt_sha256": item.failure_receipt_sha256,
                "prior_failure_attempts": [dict(attempt) for attempt in item.prior_failure_attempts],
                "diagnostic": item.diagnostic,
            }
            for item in result.markets
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.status == "captured" else 2


if __name__ == "__main__":
    raise SystemExit(main())
