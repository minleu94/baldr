"""唯讀驗收固定 WP5 官方日行情 capture，僅輸出 JSON。"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_module.wp5_official_daily_capture_validator import (  # noqa: E402
    CAPTURE_DIRECTORY_NAME,
    CaptureValidationError,
    blocked_result,
    validate_official_daily_capture,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "唯讀驗證固定 2026-09-29 TWSE/TPEx 官方 raw capture，"
            "stdout 只輸出同日市場活動 evidence JSON。"
        )
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        default=Path("output") / "qa" / CAPTURE_DIRECTORY_NAME,
    )
    parser.add_argument("--expected-receipt-sha256", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--decision-date", type=date.fromisoformat, required=True)
    parser.add_argument("--required-twse-symbol", default="2330")
    parser.add_argument("--required-tpex-symbol", default="6488")
    parser.add_argument(
        "--cutoff-utc",
        help="可選 ISO-8601 UTC cutoff；省略時使用本機目前 UTC 時鐘。",
    )
    return parser


def _parse_cutoff(value: str | None, *, now_utc: datetime) -> datetime:
    if value is None:
        return now_utc
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CaptureValidationError(
            "cutoff_utc_invalid", "cutoff 必須是含時區的 ISO-8601 時間。"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CaptureValidationError(
            "cutoff_utc_timezone_missing", "cutoff 必須明確包含 UTC offset。"
        )
    return parsed.astimezone(timezone.utc)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    now_utc = datetime.now(timezone.utc)
    try:
        cutoff_utc = _parse_cutoff(args.cutoff_utc, now_utc=now_utc)
        result = validate_official_daily_capture(
            args.capture_dir,
            expected_receipt_sha256=args.expected_receipt_sha256,
            expected_manifest_sha256=args.expected_manifest_sha256,
            decision_date=args.decision_date,
            required_symbols_by_venue={
                "TWSE": args.required_twse_symbol,
                "TPEx": args.required_tpex_symbol,
            },
            cutoff_utc=cutoff_utc,
            repo_root=REPO_ROOT,
        )
    except CaptureValidationError as error:
        result = blocked_result(error)
    except (OSError, ValueError) as error:
        result = blocked_result(
            CaptureValidationError("validator_input_invalid", str(error))
        )
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result.get("status") == "validated" else 2


if __name__ == "__main__":
    raise SystemExit(main())
