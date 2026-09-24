"""2026-09-11 Phase3C candidate institutional controlled repair CLI。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from data_module.phase3c_candidate_repair import (  # noqa: E402
    CandidateRepairError,
    apply_plan,
    build_plan,
    read_history_as_of,
    rollback_receipt,
)


def _path(value: str) -> Path:
    return Path(value).expanduser()


def _common_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--production-data-root", required=True, type=_path)
    parser.add_argument("--formal-db", required=True, type=_path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="candidate-only 2026-09-11 institutional repair；預設只建立 plan。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="唯讀驗證 capture/candidate preimage 並建立 plan")
    plan.add_argument("--capture-manifest", required=True, type=_path)
    plan.add_argument("--candidate-db", required=True, type=_path)
    plan.add_argument("--receipt-dir", required=True, type=_path)
    _common_target(plan)

    apply = subparsers.add_parser("apply", help="staging 驗證後套用 candidate repair")
    apply.add_argument("--plan", required=True, type=_path)
    apply.add_argument("--confirm", required=True)
    _common_target(apply)

    rollback = subparsers.add_parser("rollback", help="只回復本輪 rows/checkpoint/history")
    rollback.add_argument("--receipt", required=True, type=_path)
    rollback.add_argument("--confirm", required=True)
    _common_target(rollback)

    history = subparsers.add_parser("history", help="唯讀依 custody timestamp 查回歷史 row")
    history.add_argument("--candidate-db", required=True, type=_path)
    history.add_argument("--as-of", required=True)
    history.add_argument("--stock-code")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "plan":
            result = build_plan(
                capture_manifest=args.capture_manifest,
                candidate_db=args.candidate_db,
                production_data_root=args.production_data_root,
                formal_db=args.formal_db,
                receipt_dir=args.receipt_dir,
            )
        elif args.command == "apply":
            result = apply_plan(
                plan_path=args.plan,
                confirm=args.confirm,
                production_data_root=args.production_data_root,
                formal_db=args.formal_db,
            )
        elif args.command == "rollback":
            result = rollback_receipt(
                receipt_path=args.receipt,
                confirm=args.confirm,
                production_data_root=args.production_data_root,
                formal_db=args.formal_db,
            )
        else:
            result = read_history_as_of(
                candidate_db=args.candidate_db,
                as_of=args.as_of,
                stock_code=args.stock_code,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    except (CandidateRepairError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
