"""具名v4來源的複製／封存恢復；不抓取、不重算或啟用新設定。"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_module.research_output_copy import ResearchOutputCopyBudget
from app_module.technical_source_copy import TechnicalSourcePin, copy_technical_source, restore_technical_source


def main() -> int:
    parser = argparse.ArgumentParser(description="複製具名完整technical v4來源，或恢復已移位的完整封存包；原件保留。")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-pin", type=Path)
    source.add_argument("--archive-directory", type=Path)
    parser.add_argument("--source-sha256", required=True, help="source-pin檔或封存TECHNICAL_COPY_RECEIPT.json的外部固定SHA")
    parser.add_argument("--destination-root", type=Path, required=True)
    parser.add_argument("--max-file-bytes", type=int, default=256 * 1024**2)
    parser.add_argument("--max-total-bytes", type=int, default=4 * 1024**3)
    parser.add_argument("--max-entries", type=int, default=100000)
    parser.add_argument("--max-parents", type=int, default=391)
    args = parser.parse_args()
    budget = ResearchOutputCopyBudget(args.max_file_bytes, args.max_total_bytes, args.max_entries, args.max_parents)
    if args.source_pin:
        with args.source_pin.open("rb") as stream:
            raw = stream.read(64 * 1024 + 1)
        if len(raw) > 64 * 1024 or sha256(raw).hexdigest() != args.source_sha256:
            parser.error("來源pin檔超限或SHA不符")
        pin = copy_technical_source(TechnicalSourcePin.from_dict(json.loads(raw)), args.destination_root, budget=budget)
    else:
        pin = restore_technical_source(args.archive_directory, args.source_sha256, args.destination_root, budget=budget)
    print(json.dumps({"copied_pin": pin.to_dict(), "configuration_activated": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
