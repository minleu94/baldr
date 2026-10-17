"""只複製明選的離線保存研究；不自動啟用新根或修改正式設定。"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_module.research_output_copy import ResearchOutputCopyBudget, copy_research_output, restore_research_output


def main() -> int:
    parser = argparse.ArgumentParser(description="建立離線保存研究的新副本，原件唯讀；非完整資料環境移機。")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-output-root", type=Path)
    source.add_argument("--archive-directory", type=Path, help="已移位的完整RESEARCH_COPY_RECEIPT封存目錄")
    parser.add_argument("--archive-receipt-sha256", help="封存前另存的外部固定收據SHA")
    parser.add_argument("--destination-output-root", type=Path, required=True)
    parser.add_argument("--include-recommendations", action="store_true", help="另明選一般保存推薦（legacy與canonical）；外部ML收據依賴未核時拒絕此批")
    parser.add_argument("--max-file-bytes", type=int, default=256 * 1024**2)
    parser.add_argument("--max-total-bytes", type=int, default=4 * 1024**3)
    parser.add_argument("--max-entries", type=int, default=100000)
    parser.add_argument("--max-runs", type=int, default=10000)
    args = parser.parse_args()
    budget = ResearchOutputCopyBudget(args.max_file_bytes, args.max_total_bytes, args.max_entries, args.max_runs)
    if args.archive_directory:
        if args.archive_receipt_sha256 is None or args.include_recommendations:
            parser.error("封存恢復須提供外部收據SHA；store範圍沿原封存，不再加選推薦")
        receipt = restore_research_output(args.archive_directory, args.archive_receipt_sha256,
                                         args.destination_output_root, budget=budget)
    else:
        if args.archive_receipt_sha256 is not None:
            parser.error("--archive-receipt-sha256只能配--archive-directory")
        receipt = copy_research_output(args.source_output_root, args.destination_output_root, budget=budget,
                                      include_recommendations=args.include_recommendations)
    print("新副本已由原reader核對；未啟用新根。收據：" + str(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
