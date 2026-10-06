"""SQLite 觀察清單 COW 副本、明示啟用與回滾入口；預覽不寫資料。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence, TypedDict, NotRequired, TYPE_CHECKING

if TYPE_CHECKING:
    from app_module.personal_data_paths import WatchlistCowControlPaths


class _ControlOptions(TypedDict):
    control_paths: NotRequired[WatchlistCowControlPaths]

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="觀察清單SQLite COW遷移；先dry-run，再明示convert與activate。原DB不覆寫、不刪除。")
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("dry-run", "convert", "activation-preview", "activate", "status", "rollback"):
        child = actions.add_parser(action)
        child.add_argument("--personal-root", type=Path)
        child.add_argument("--market-root", type=Path)
        child.add_argument("--legacy-output-root", type=Path)
        child.add_argument("--source", type=Path, required=True, help="來源SQLite DB；僅明示legacy-json時為單一JSON檔")
        if action in {"dry-run", "convert", "activation-preview", "activate"}:
            child.add_argument("--destination", type=Path, required=True, help="獨立新v3 DB路徑；不能等於原檔")
        if action in {"dry-run", "convert"}:
            child.add_argument(
                "--source-format", choices=("sqlite", "legacy-json"), default="sqlite",
                help="輸入格式；預設sqlite，legacy-json只轉換指定的單一JSON檔",
            )
        if action in {"activation-preview", "activate"}:
            child.add_argument("--receipt", type=Path, help="副本核驗收據；預設target.cow-conversion.v1.json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        controls = None
        roots = (args.personal_root, args.market_root, args.legacy_output_root)
        if any(value is not None for value in roots):
            if not all(value is not None for value in roots):
                raise ValueError("personal_storage_selection_incomplete")
            from app_module.personal_data_paths import (
                resolve_personal_data_paths, WatchlistCowControlPaths,
            )
            paths = resolve_personal_data_paths(
                args.market_root, personal_root=args.personal_root,
                legacy_output_root=args.legacy_output_root, environ={},
            )
            root = paths.personal_root
            if root == ROOT or ROOT in root.parents or root in ROOT.parents:
                raise ValueError("personal_root_overlaps_application_package")
            controls = WatchlistCowControlPaths(paths, args.source)
        options: _ControlOptions = {"control_paths": controls} if controls is not None else {}
        if args.action in {"dry-run", "convert"}:
            if args.source_format == "legacy-json":
                from data_module.watchlist_json_cow import convert_watchlist_json, dry_run_watchlist_json
                operation = dry_run_watchlist_json if args.action == "dry-run" else convert_watchlist_json
            else:
                from data_module.watchlist_sqlite_cow import convert_watchlist_sqlite, dry_run_watchlist_sqlite
                operation = dry_run_watchlist_sqlite if args.action == "dry-run" else convert_watchlist_sqlite
            result = operation(args.source, args.destination, **options)
        else:
            from app_module.watchlist_cow_activation import (
                activate_watchlist_sqlite, preview_watchlist_sqlite_activation,
                resolve_watchlist_sqlite_activation, rollback_watchlist_sqlite,
            )
            if args.action == "activation-preview":
                result = preview_watchlist_sqlite_activation(args.source, args.destination, receipt_path=args.receipt, **options)
            elif args.action == "activate":
                result = activate_watchlist_sqlite(args.source, args.destination, receipt_path=args.receipt, **options)
            elif args.action == "rollback":
                result = rollback_watchlist_sqlite(args.source, **options)
            else:
                result = resolve_watchlist_sqlite_activation(args.source, **options)
    except Exception as exc:
        result = {"status": "blocked", "code": str(getattr(exc, "code", type(exc).__name__)), "error_type": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 2 if result.get("status") == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
