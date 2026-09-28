"""明確注入來源後，發布已保存個人推薦的成熟自然結果。"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.recommendation.personal_natural_outcome_daily import (  # noqa: E402
    MAX_CAPTURE_PATHS,
    PersonalNaturalOutcomeDailyError,
    run_personal_natural_outcome_daily,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "逐一嚴格讀回明確指定的個人 prediction capture；只有完整成熟的 20 個"
            "官方 session 結果會 create-only 發布至隔離個人 lane。"
        )
    )
    parser.add_argument(
        "--canonical-recommendation-output-root",
        type=Path,
        required=True,
        help="canonical 產品 OUTPUT_ROOT，內含 recommendation/runs/。",
    )
    parser.add_argument(
        "--capture-path",
        type=Path,
        action="append",
        required=True,
        help=(
            "要處理的 personal_capture_root/captures 直屬 JSON 檔；可重複，最多 "
            f"{MAX_CAPTURE_PATHS} 個，不掃描 latest 或 glob。"
        ),
    )
    parser.add_argument(
        "--personal-capture-root",
        type=Path,
        required=True,
        help="Stage A 個人捕獲根目錄，內含 captures/。",
    )
    parser.add_argument("--market-source-db", type=Path, required=True)
    parser.add_argument(
        "--calendar-cache-path",
        type=Path,
        required=True,
        help="官方 annual calendar cache 目錄或明確 cache 檔；不以平日推算官方 session。",
    )
    parser.add_argument(
        "--temporary-closure-cache-path",
        type=Path,
        default=None,
        help=(
            "可選官方 temporary-closure cache 目錄或檔案；省略時證據標為 "
            "annual_plan_only。"
        ),
    )
    parser.add_argument(
        "--evaluation-at",
        required=True,
        help="必填含時區的 ISO datetime，例如 2026-09-27T16:00:00+08:00。",
    )
    parser.add_argument(
        "--isolated-output-root",
        type=Path,
        required=True,
        help="與 canonical/capture/market/calendar 路徑樹分離的個人輸出根目錄。",
    )
    return parser


def _parse_evaluation_at(raw: str) -> datetime:
    value = str(raw).strip()
    if not value:
        raise ValueError("evaluation_at 不可空白")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("evaluation_at 必須明確含時區")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        evaluation_at = _parse_evaluation_at(args.evaluation_at)
        receipt = run_personal_natural_outcome_daily(
            canonical_recommendation_output_root=args.canonical_recommendation_output_root,
            capture_paths=args.capture_path,
            personal_capture_root=args.personal_capture_root,
            market_source_db=args.market_source_db,
            calendar_cache_path=args.calendar_cache_path,
            temporary_closure_cache_path=args.temporary_closure_cache_path,
            evaluation_at=evaluation_at,
            isolated_output_root=args.isolated_output_root,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        payload = {
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 2

    payload = {
        "status": receipt.status,
        "summary_path": str(receipt.summary_path),
        "summary_sha256": receipt.summary_sha256,
        "summary_idempotent": receipt.summary_idempotent,
        "outcomes": [
            {
                "path": str(path),
                "payload_sha256": digest,
                "idempotent": idempotent,
            }
            for path, digest, idempotent in zip(
                receipt.outcome_paths,
                receipt.outcome_sha256s,
                receipt.idempotent_outcomes,
            )
        ],
        "capture_statuses": list(receipt.capture_statuses),
        "global_natural_evidence_created": False,
        "promotion_credit_created": False,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 2 if receipt.status == "completed_with_unknown" else 0


if __name__ == "__main__":
    raise SystemExit(main())
