"""只複製明選的離線保存研究；不自動啟用新根或修改正式設定。"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_module.research_output_copy import ResearchOutputCopyBudget, copy_research_output


def main() -> int:
    parser = argparse.ArgumentParser(description="建立離線保存研究的新副本，原件唯讀；非完整資料環境移機。")
    parser.add_argument("--source-output-root", type=Path, required=True)
    parser.add_argument("--destination-output-root", type=Path, required=True)
    parser.add_argument("--max-file-bytes", type=int, default=256 * 1024**2)
    parser.add_argument("--max-total-bytes", type=int, default=4 * 1024**3)
    parser.add_argument("--max-entries", type=int, default=100000)
    parser.add_argument("--max-runs", type=int, default=10000)
    args = parser.parse_args()
    budget = ResearchOutputCopyBudget(args.max_file_bytes, args.max_total_bytes, args.max_entries, args.max_runs)
    receipt = copy_research_output(args.source_output_root, args.destination_output_root, budget=budget)
    print("新副本已由原reader核對；未啟用新根。收據：" + str(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
