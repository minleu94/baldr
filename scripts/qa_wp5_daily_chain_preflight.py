"""Emit a read-only JSON preflight for one isolated WP5 daily QA root."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_module.wp5_daily_chain_preflight import (  # noqa: E402
    PreflightConfig,
    run_read_only_preflight,
)


def _aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "唯讀核對 WP5 QA root、seed pin、SQLite ro/query_only 與當日官方證據；"
            "只輸出 JSON，不建立任何檔案或目錄。"
        )
    )
    parser.add_argument("--qa-root", type=Path, required=True)
    parser.add_argument("--decision-date", type=date.fromisoformat, required=True)
    parser.add_argument("--observed-at-utc", type=_aware_datetime, required=True)
    parser.add_argument("--expected-bootstrap-receipt-sha256", required=True)
    parser.add_argument("--expected-working-db-sha256", required=True)
    parser.add_argument("--expected-snapshot-receipt-sha256", required=True)
    parser.add_argument("--calendar-cache-path", type=Path)
    parser.add_argument("--temporary-closure-path", type=Path)
    parser.add_argument("--source-time-receipt", type=Path)
    parser.add_argument(
        "--skip-candidate-update",
        action="store_true",
        help="明確證明本 QA preflight 不會解析 candidate DB/HKCU fallback",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_read_only_preflight(
            PreflightConfig(
                qa_root=args.qa_root,
                decision_date=args.decision_date,
                observed_at=args.observed_at_utc,
                expected_bootstrap_receipt_sha256=(
                    args.expected_bootstrap_receipt_sha256
                ),
                expected_working_db_sha256=args.expected_working_db_sha256,
                expected_snapshot_receipt_sha256=(
                    args.expected_snapshot_receipt_sha256
                ),
                calendar_cache_path=args.calendar_cache_path,
                temporary_closure_path=args.temporary_closure_path,
                source_time_receipt_path=args.source_time_receipt,
                skip_candidate_update=args.skip_candidate_update,
                repo_root=REPO_ROOT,
            )
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] == "ready" else 2
    except Exception as error:
        print(
            json.dumps(
                {
                    "schema_version": "wp5-qa-root-read-only-preflight.v1",
                    "status": "blocked",
                    "blockers": [
                        {
                            "scope": "preflight",
                            "code": "preflight_input_or_inspection_error",
                            "detail": str(error),
                        }
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
