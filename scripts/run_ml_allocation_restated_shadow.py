"""用明確指定的模型／修訂資料身分執行當日研究判讀。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.restated_allocation_shadow_service import run_restated_current_shadow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="使用修訂模型執行當日研究判讀；不啟用正式交易。")
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--release-identity-hash", required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--dataset-manifest-hash", required=True)
    parser.add_argument("--source-db", type=Path, help="選用：先從唯讀 SQLite 封存新的當日輸入；dataset manifest 此時作固定特徵契約範本。")
    parser.add_argument("--price-repair-receipt", type=Path)
    parser.add_argument("--price-repair-receipt-hash")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = args.dataset_manifest
    manifest_hash = args.dataset_manifest_hash
    if args.source_db is not None:
        if args.price_repair_receipt is None or args.price_repair_receipt_hash is None:
            parser.error("--source-db 需要 --price-repair-receipt 與 --price-repair-receipt-hash")
        from data_module.ml_restatement_current_capture import capture_restated_current_dataset

        manifest, manifest_hash = capture_restated_current_dataset(
            database_path=args.source_db,
            template_manifest_path=manifest,
            expected_template_manifest_hash=manifest_hash,
            price_repair_receipt=args.price_repair_receipt,
            expected_price_receipt_hash=args.price_repair_receipt_hash,
            symbols=args.symbols,
            output_root=args.output_root / "input_captures",
        )
    elif args.price_repair_receipt is not None or args.price_repair_receipt_hash is not None:
        parser.error("修訂 receipt 參數須與 --source-db 一起使用")
    result = run_restated_current_shadow(
        release_root=args.release_root,
        expected_release_identity_hash=args.release_identity_hash,
        dataset_manifest=manifest,
        expected_dataset_manifest_hash=manifest_hash,
        symbols=args.symbols,
        output_root=args.output_root,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
