"""UX23 隔離研究驗收：預覽、明示保存及 exact 收據重讀。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.rule_research_shadow_acceptance import (
    build_shadow_acceptance, read_shadow_acceptance, save_shadow_acceptance,
)
from scripts.run_rule_research_fair_comparison import _bundle
from scripts.run_rule_research_label_readiness import _config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="隔離 shadow 工程驗收；始終未啟用正式行為")
    parser.add_argument("--receipt", nargs=2, action="append", metavar=("PARENT", "OUTCOME"))
    parser.add_argument("--case-id")
    parser.add_argument("--label-policy")
    parser.add_argument("--split-policy")
    parser.add_argument("--comparison-policy")
    parser.add_argument("--inputs-bundle")
    parser.add_argument("--lifecycle-export", help="明示 registry DTO 匯出；不連線資料庫")
    parser.add_argument("--stop-reason", help="僅停止本次隔離研究投影，保留規則路徑")
    parser.add_argument("--store", help="output/qa 或系統 Temp 的獨立子目錄")
    parser.add_argument("--save", action="store_true", help="明示保存不可變研究收據")
    parser.add_argument("--identity", help="重讀指定原始 64 位 SHA；不讀 latest")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.identity is not None:
            if not args.store or args.save or any((args.receipt, args.case_id, args.label_policy,
                    args.split_policy, args.comparison_policy, args.inputs_bundle,
                    args.lifecycle_export, args.stop_reason)):
                raise ValueError("exact_read_requires_only_store_and_identity")
            result = read_shadow_acceptance(args.store, args.identity)
            summary = result["capture"]["summary_text"]
        else:
            if not args.receipt or not args.case_id or len(args.receipt) > 32:
                raise ValueError("explicit_case_and_bounded_receipts_required")
            if args.save != bool(args.store):
                raise ValueError("save_requires_explicit_isolated_store")
            def build():
                # 每次重新開啟所有 JSON 與 exact 收據，保存前後不沿用快取。
                return build_shadow_acceptance(
                    [(Path(parent), Path(outcome)) for parent, outcome in args.receipt],
                    case_id=args.case_id, label_policy=_config(args.label_policy),
                    split_policy=_config(args.split_policy),
                    comparison_policy=_config(args.comparison_policy),
                    bundle=_bundle(args.inputs_bundle),
                    lifecycle_export=_config(args.lifecycle_export), stop_reason=args.stop_reason)
            report = build()
            summary = report["summary_text"]
            result = save_shadow_acceptance(report, args.store, revalidate=build) if args.save else report
        if args.json:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False))
        else:
            print(summary)
            if args.save:
                print(f"隔離收據：{result['receipt']['capture_identity_sha256']}（{result['status']}）")
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        result = {"status": "rejected", "reason": str(exc), "shadow_enabled": False,
                  "production_action_allowed": False, "formal_eligible": False,
                  "training_eligible": False, "historical_pit_eligible": False,
                  "natural_authority": False, "execution_eligible": False,
                  "production_blend_alpha_bp": 0, "qualified_count": 0,
                  "selection_status": "unknown"}
        print(json.dumps(result, ensure_ascii=False) if args.json else
              f"工程未完成：保留規則路徑／資料或效果未合格／未啟用（{exc}）")
        return 2


if __name__ == "__main__":
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    raise SystemExit(main())
