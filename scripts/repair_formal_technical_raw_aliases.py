"""以 run02 已核驗日價修復技術快取六欄；預設所有階段都先驗證來源。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from data_module.formal_technical_raw_alias_repair import (
    CONFIRM,
    RawAliasRepairError,
    apply,
    audit,
    prepare,
    recover,
    stage,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="正式 DATA_ROOT；prepare 必填")
    parser.add_argument("--technical-receipt-dir", type=Path, help="已套用的 run02 技術修復 receipt 目錄")
    parser.add_argument("--receipt-dir", type=Path, required=True, help="本次 raw alias 修復紀錄目錄")
    parser.add_argument("--expected-manifest-hash", help="stage/manifest.json 的 SHA-256")
    parser.add_argument("--confirm", help="apply/resume/rollback 的明確確認字串")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true", help="驗證 run02 applied 證據並建立紀錄")
    modes.add_argument("--stage", action="store_true", help="串流建立 DB spool 與 CSV staging")
    modes.add_argument("--audit", action="store_true", help="全量核對每個 key、欄位與非目標內容")
    modes.add_argument("--apply", action="store_true", help="原子交易發布 SQLite 六欄並逐檔發布 CSV")
    modes.add_argument("--resume", action="store_true", help="依 journal 恢復 pending 發布")
    modes.add_argument("--rollback", action="store_true", help="依完整 preimage 回復已套用修復")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.prepare:
            if args.root is None or args.technical_receipt_dir is None:
                parser.error("--prepare 需要 --root 與 --technical-receipt-dir")
            root = args.root or Path(os.environ.get("DATA_ROOT", "F:/Min/Python/Project/FA_Data"))
            result = prepare(root, args.technical_receipt_dir, args.receipt_dir)
        elif args.stage:
            result = stage(args.receipt_dir)
        elif args.audit:
            result = audit(args.receipt_dir, args.expected_manifest_hash)
        else:
            if args.confirm != CONFIRM:
                parser.error("apply/resume/rollback 需要正確的 --confirm")
            if not args.expected_manifest_hash:
                parser.error("apply/resume/rollback 需要 --expected-manifest-hash")
            if args.apply:
                result = apply(args.receipt_dir, args.expected_manifest_hash)
            else:
                result = recover(
                    args.receipt_dir,
                    rollback=bool(args.rollback),
                    expected_manifest_hash=args.expected_manifest_hash,
                )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
        return 0
    except (OSError, RawAliasRepairError, ValueError) as exc:
        print(json.dumps({"state": "rejected", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
