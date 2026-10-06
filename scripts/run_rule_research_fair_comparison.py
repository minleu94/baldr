"""同源封存研究比較：預設白話摘要，--json 保存有界診斷收據。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.rule_research_fair_comparison import build_fair_comparison
from scripts.run_rule_research_label_readiness import _config, _unique_object

MAX_BUNDLE_BYTES = 2 * 1024 * 1024


def _bundle(path: str | None):
    if path is None:
        return None
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BUNDLE_BYTES + 1)
    if len(raw) > MAX_BUNDLE_BYTES:
        raise ValueError("fair_inputs_bundle_byte_bound")
    value = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError("fair_inputs_bundle_object_required")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ML目前能否同源比較、差在哪、缺什麼；不訓練、不寫registry")
    parser.add_argument("--receipt", nargs=2, action="append", required=True, metavar=("PARENT", "OUTCOME"))
    parser.add_argument("--label-policy")
    parser.add_argument("--split-policy")
    parser.add_argument("--comparison-policy", help="明示method／horizon／metric／k及可選downside政策")
    parser.add_argument("--inputs-bundle", help="同源CORE20 feature與既有baseline／candidate prediction DTO JSON")
    parser.add_argument("--json", action="store_true", help="完整診斷JSON；可保存並以同輸入新程序核對identity")
    args = parser.parse_args(argv)
    try:
        if len(args.receipt) > 32:
            raise ValueError("fair_receipt_count_bound")
        result = build_fair_comparison(
            [(Path(parent), Path(outcome)) for parent, outcome in args.receipt],
            label_policy=_config(args.label_policy), split_policy=_config(args.split_policy),
            comparison_policy=_config(args.comparison_policy), bundle=_bundle(args.inputs_bundle))
        if args.json:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
        else:
            print(result["summary_text"])
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        if args.json:
            print(json.dumps({"status": "rejected", "reason": str(exc),
                "training_eligible": False, "formal_eligible": False}, ensure_ascii=False))
        else:
            print(f"目前無法比較：輸入不合格（{exc}）。未進行模型訓練或正式發布。")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
