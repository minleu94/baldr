"""為明選價格研究收藏建立新來源副本；原收藏與原清單保留。"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_module.research_output_copy import ResearchOutputCopyBudget
from app_module.technical_source_copy import copy_price_bookmarks


def main() -> int:
    parser = argparse.ArgumentParser(description="明選F07收藏與已完成技術來源副本；新ID另存，不改原清單或啟用設定。")
    parser.add_argument("--source-watchlist", type=Path, required=True)
    parser.add_argument("--source-watchlist-sha256", required=True)
    parser.add_argument("--technical-copy-directory", type=Path, required=True)
    parser.add_argument("--technical-copy-receipt-sha256", required=True)
    parser.add_argument("--bookmark-id", action="append", required=True)
    parser.add_argument("--destination-output-root", type=Path, required=True)
    parser.add_argument("--max-file-bytes", type=int, default=256 * 1024**2)
    parser.add_argument("--max-total-bytes", type=int, default=4 * 1024**3)
    parser.add_argument("--max-entries", type=int, default=100000)
    parser.add_argument("--max-bookmarks", type=int, default=391)
    args = parser.parse_args()
    budget = ResearchOutputCopyBudget(args.max_file_bytes, args.max_total_bytes, args.max_entries, args.max_bookmarks)
    receipt = copy_price_bookmarks(args.source_watchlist, args.source_watchlist_sha256,
        args.technical_copy_directory, args.technical_copy_receipt_sha256, args.destination_output_root,
        bookmark_ids=args.bookmark_id, budget=budget)
    print("新價格收藏副本已核對；未啟用設定。收據：" + str(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
