"""SQLite 觀察清單 COW 副本、明示啟用與回滾入口；預覽不寫資料。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="觀察清單SQLite COW遷移；先dry-run，再明示convert與activate。原DB不覆寫、不刪除。")
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("dry-run", "convert", "activation-preview", "activate", "status", "rollback"):
        child = actions.add_parser(action)
        child.add_argument("--source", type=Path, required=True, help="原canonical SQLite DB路徑；不讀JSON替代")
        if action in {"dry-run", "convert", "activation-preview", "activate"}:
            child.add_argument("--destination", type=Path, required=True, help="獨立新v3 DB路徑；不能等於原檔")
        if action in {"activation-preview", "activate"}:
            child.add_argument("--receipt", type=Path, help="副本核驗收據；預設target.cow-conversion.v1.json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action in {"dry-run", "convert"}:
            from data_module.watchlist_sqlite_cow import convert_watchlist_sqlite, dry_run_watchlist_sqlite
            operation = dry_run_watchlist_sqlite if args.action == "dry-run" else convert_watchlist_sqlite
            result = operation(args.source, args.destination)
        else:
            from app_module.watchlist_cow_activation import (
                activate_watchlist_sqlite, preview_watchlist_sqlite_activation,
                resolve_watchlist_sqlite_activation, rollback_watchlist_sqlite,
            )
            if args.action == "activation-preview":
                result = preview_watchlist_sqlite_activation(args.source, args.destination, receipt_path=args.receipt)
            elif args.action == "activate":
                result = activate_watchlist_sqlite(args.source, args.destination, receipt_path=args.receipt)
            elif args.action == "rollback":
                result = rollback_watchlist_sqlite(args.source)
            else:
                result = resolve_watchlist_sqlite_activation(args.source)
    except Exception as exc:
        result = {"status": "blocked", "code": str(getattr(exc, "code", type(exc).__name__)), "error_type": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 2 if result.get("status") == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
