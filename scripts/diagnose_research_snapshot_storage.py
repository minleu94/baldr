"""執行研究快照儲存唯讀診斷並輸出受控路徑收據。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.research_snapshot_storage_governance import (  # noqa: E402
    diagnose_research_snapshot_storage,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="唯讀盤點 feature/rank snapshots、Watchlist pins、bytes 預算及 dry-run 候選。"
    )
    parser.add_argument("--snapshot-root", type=Path, required=True, help="feature snapshot root")
    parser.add_argument("--rank-root", type=Path, help="rank root；省略時使用 snapshot-root/original_rankings")
    parser.add_argument("--watchlist-dir", type=Path, help="完整 Watchlist JSON/SQLite extension 來源目錄")
    parser.add_argument(
        "--watchlist-inventory-complete",
        action="store_true",
        help="明示 --watchlist-dir 已列出全部 current/history Watchlist 來源",
    )
    parser.add_argument("--output", type=Path, help="收據路徑；限 output/qa/research_snapshot_storage_governance/ 內")
    return parser


def _controlled_output(value: Path | None) -> Path:
    output_root = (ROOT / "output" / "qa" / "research_snapshot_storage_governance").resolve()
    if value is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        return output_root / f"diagnosis-{stamp}-{uuid4().hex[:8]}.json"
    destination = value.expanduser()
    if not destination.is_absolute():
        destination = ROOT / destination
    destination = destination.resolve(strict=False)
    if destination != output_root and output_root not in destination.parents:
        raise ValueError(f"output 必須位於受控路徑 {output_root}")
    return destination


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    try:
        output = _controlled_output(args.output)
        receipt = diagnose_research_snapshot_storage(
            args.snapshot_root,
            rank_root=args.rank_root,
            watchlist_dir=args.watchlist_dir,
            watchlist_inventory_complete=args.watchlist_inventory_complete,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    except (OSError, ValueError) as exc:
        print(f"診斷未完成：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"receipt": str(output), "scan_complete": receipt["storage"]["scan_complete"],
                      "references_complete": receipt["storage"]["references_complete"],
                      "candidate_count": len(receipt["dry_run_candidates"]),
                      "automatic_action": receipt["automatic_action"]}, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["storage"]["scan_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
