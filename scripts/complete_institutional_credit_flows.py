"""補齊三大法人與信用交易官方候選資料的受控入口。

``capture`` 只保存 repo ignored output 的官方 raw bytes／candidate manifest；
``apply`` 必須由 owner 明確提供 manifest、SQLite 路徑與確認 token，才會
以 idempotent transaction 匯入指定表。此腳本不會猜測正式 DB，也不會自行
呼叫 apply。
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_module.institutional_credit_flows_service import (
    APPLY_CONFIRM_TOKEN,
    DEFAULT_OUTPUT_ROOT,
    FLOW_CAPTURE_SCOPES,
    apply_flow_manifest,
    capture_recent_flows,
    rebuild_flow_manifest_from_raw,
)


def _today_taipei() -> date:
    return datetime.now(ZoneInfo("Asia/Taipei")).date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture/apply official TWSE and TPEx institutional/credit candidate flows"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture", help="只捕捉 raw/candidate，不寫 SQLite")
    capture.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    capture.add_argument("--as-of-date", default=None, help="YYYY-MM-DD；預設台北今日")
    capture.add_argument("--sessions", type=int, default=10)
    capture.add_argument("--max-lookback-days", type=int, default=45)
    capture.add_argument("--timeout-seconds", type=int, default=30)
    capture.add_argument("--max-attempts", type=int, default=2)
    capture.add_argument("--rate-limit-seconds", type=float, default=0.25)
    capture.add_argument(
        "--capture-scope", choices=FLOW_CAPTURE_SCOPES, default="legacy_all",
        help="twse_institutional 僅保存 TWSE 法人候選；legacy_all 保留原四來源行為",
    )

    rebuild = subparsers.add_parser(
        "rebuild", help="從既有 raw/metadata 重播 candidate，不重新發 HTTP"
    )
    rebuild.add_argument("--run-dir", required=True, help="既有 capture run 目錄")
    rebuild.add_argument("--manifest-name", default="manifest.json")

    seal = subparsers.add_parser("seal", help="核原TWSE法人capture，保存新批次小時收據；不抓取／apply")
    seal.add_argument("--run-dir", required=True, help="原twse_institutional capture的絕對目錄")
    seal.add_argument("--capture-manifest-sha256", required=True)

    apply = subparsers.add_parser("apply", help="顯式匯入已審核 candidate manifest")
    apply.add_argument("--manifest", required=True, help="capture 產出的 manifest.json")
    apply.add_argument("--db-path", required=True, help="明確 SQLite 目標；不猜測")
    apply.add_argument(
        "--confirm",
        required=True,
        help=f"必須為 {APPLY_CONFIRM_TOKEN}",
    )
    apply.add_argument("--receipt-path", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    if args.command == "capture":
        target_date = date.fromisoformat(args.as_of_date) if args.as_of_date else _today_taipei()
        result = capture_recent_flows(
            output_root=args.output_root,
            as_of_date=target_date,
            sessions=args.sessions,
            max_lookback_days=args.max_lookback_days,
            timeout_seconds=args.timeout_seconds,
            max_attempts=args.max_attempts,
            rate_limit_seconds=args.rate_limit_seconds,
            capture_scope=args.capture_scope,
        )
    elif args.command == "rebuild":
        result = rebuild_flow_manifest_from_raw(
            args.run_dir,
            manifest_name=args.manifest_name,
        )
    elif args.command == "seal":
        from app_module.institutional_daily_snapshot import seal_twse_institutional_capture
        pin = seal_twse_institutional_capture(Path(args.run_dir), args.capture_manifest_sha256)
        result = {"directory": str(pin.directory), "manifest_sha256": pin.manifest_sha256,
                  "receipt_sha256": pin.receipt_sha256, "candidate_only": True,
                  "source_use_accepted": False, "historical_pit_eligible": False}
    else:
        result = apply_flow_manifest(
            args.manifest,
            db_path=args.db_path,
            confirm_token=args.confirm,
            receipt_path=args.receipt_path,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
