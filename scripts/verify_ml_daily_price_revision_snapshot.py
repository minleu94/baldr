"""為隔離 SQLite 快照產生 2026-05-20 修訂後技術資料唯讀驗收。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_module.ml_daily_price_revision_technical_snapshot import (
    SnapshotEvidenceError,
    verify_revision_snapshot,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-snapshot", required=True, type=Path)
    parser.add_argument("--technical-pending", required=True, type=Path)
    parser.add_argument("--technical-receipt", required=True, type=Path)
    parser.add_argument("--price-pending", required=True, type=Path)
    parser.add_argument("--price-receipt", required=True, type=Path)
    parser.add_argument("--technical-backup", required=True, type=Path)
    parser.add_argument("--dryrun-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = args.output.expanduser().resolve(strict=False)
    sources = (
        args.database_snapshot, args.technical_pending, args.technical_receipt,
        args.price_pending, args.price_receipt, args.technical_backup,
        args.dryrun_manifest,
    )
    if output.drive.casefold() != args.database_snapshot.resolve().drive.casefold():
        print("拒絕將驗收 evidence 寫入 SQLite snapshot 所在磁碟以外的位置。", file=sys.stderr)
        return 2
    output_parent = output.parent.resolve(strict=False)
    for source in sources:
        source_path = source.resolve()
        source_parent = source_path.parent
        if (output == source_path or output_parent == source_parent
            or output_parent in source_path.parents or source_parent in output_parent.parents):
            print("拒絕將驗收 evidence 寫入來源路徑或與來源路徑重疊的位置。", file=sys.stderr)
            return 2
    if output.exists() or output.is_symlink():
        print("拒絕覆寫既有 evidence 檔。", file=sys.stderr)
        return 2
    try:
        evidence = verify_revision_snapshot(
            database_path=args.database_snapshot,
            technical_pending_path=args.technical_pending,
            technical_receipt_path=args.technical_receipt,
            price_pending_path=args.price_pending,
            price_receipt_path=args.price_receipt,
            technical_backup_path=args.technical_backup,
            dryrun_manifest_path=args.dryrun_manifest,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(evidence, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except (OSError, SnapshotEvidenceError) as exc:
        print(f"修訂快照驗收失敗：{exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": evidence["status"], "evidence_sha256": evidence["evidence_sha256"],
                      "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
