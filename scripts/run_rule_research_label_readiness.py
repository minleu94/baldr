"""讀取 exact 保存收據的 endpoint label readiness；不查行情、不呼叫 fit。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.rule_research_label_readiness import build_label_readiness_batch

MAX_CONFIG_BYTES = 64 * 1024
MAX_REPORT_BYTES = 2 * 1024 * 1024


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("label_config_duplicate_key")
        result[key] = value
    return result


def _config(path: str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_CONFIG_BYTES + 1)
    if len(raw) > MAX_CONFIG_BYTES:
        raise ValueError("label_config_byte_bound")
    value = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError("label_config_object_required")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="封存研究 label→樣本／公平比較 readiness；沒有模型訓練")
    parser.add_argument("--receipt", nargs=2, action="append", required=True,
                        metavar=("PARENT", "OUTCOME"), help="exact parent／outcome receipt.json；可重複，最多32對")
    parser.add_argument("--label-policy", help="明示版本化 measure／horizons JSON；省略即缺件")
    parser.add_argument("--split-policy", help="明示訓練／評估時間界線 JSON；省略即缺件")
    args = parser.parse_args(argv)
    try:
        if len(args.receipt) > 32:
            raise ValueError("label_receipt_count_bound")
        result = build_label_readiness_batch(
            [(Path(parent), Path(outcome)) for parent, outcome in args.receipt],
            policy=_config(args.label_policy), split_policy=_config(args.split_policy))
        raw = json.dumps(result, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
        if len(raw.encode("utf-8")) > MAX_REPORT_BYTES:
            raise ValueError("label_report_byte_bound")
    except (ValueError, TypeError, OSError, KeyError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc),
                          "training_eligible": False, "formal_eligible": False}, ensure_ascii=False))
        return 2
    print(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
