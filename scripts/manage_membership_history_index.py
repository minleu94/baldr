"""研究歷史派生索引的明示重建／版本回退；不遷移原資料。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_module.research_membership_history_index import (
    MembershipHistoryIndexError, default_membership_history_cache_root,
    rebuild_membership_history_index, rollback_membership_history_index,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("rebuild", "rollback"))
    parser.add_argument("--snapshot-root", required=True)
    parser.add_argument("--index-root")
    parser.add_argument("--generation-id")
    args = parser.parse_args(argv)
    source = Path(args.snapshot_root).expanduser()
    cache = Path(args.index_root).expanduser() if args.index_root else default_membership_history_cache_root(source)
    if args.action == "rollback" and not args.generation_id:
        parser.error("rollback 需要 --generation-id；只接受索引根內已完成版本")
    if args.action == "rebuild" and args.generation_id:
        parser.error("rebuild 不接受 --generation-id")
    try:
        result = (rebuild_membership_history_index(source, cache)
                  if args.action == "rebuild" else rollback_membership_history_index(source, cache, generation_id=args.generation_id))
        print(json.dumps({"status": "completed", "generation_id": result.generation_id,
                          "source_fingerprint": result.source_fingerprint,
                          "manifest_count": result.manifest_count, "activated": result.activated,
                          "index_path": str(result.index_path), "index_size_bytes": result.index_size_bytes,
                          "retained_generation_count": result.retained_generation_count,
                          "retained_generation_bytes": result.retained_generation_bytes, "research_only": True,
                          "historical_pit_eligible": False}, ensure_ascii=False))
        return 0
    except MembershipHistoryIndexError as exc:
        print(json.dumps({"status": "not_completed", "reason": exc.reason,
                          "detail": str(exc), "original_sources_preserved": True}, ensure_ascii=False))
        return 2
    except KeyboardInterrupt:
        print(json.dumps({"status": "cancelled", "original_sources_preserved": True}))
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
