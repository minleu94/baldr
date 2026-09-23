"""用原 bounded 家族的新模型執行當日研究預測。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.bounded_restated_shadow_service import (
    run_bounded_restated_current_heads,
    validate_bounded_output_root,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="原 bounded 重訓模型的當日研究預測；不產生配置或交易指令。")
    parser.add_argument("--fit-directory", type=Path, required=True)
    parser.add_argument("--fit-receipt-hash", required=True)
    parser.add_argument("--training-manifest", type=Path, required=True)
    parser.add_argument("--training-manifest-hash", required=True)
    parser.add_argument("--current-manifest", type=Path, required=True)
    parser.add_argument("--current-manifest-hash", required=True)
    parser.add_argument("--source-db", type=Path)
    parser.add_argument("--price-repair-receipt", type=Path)
    parser.add_argument("--price-repair-receipt-hash")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    validate_bounded_output_root(
        fit_directory=args.fit_directory, training_manifest=args.training_manifest,
        current_manifest=args.current_manifest, output_root=args.output_root,
    )
    current_manifest, current_hash = args.current_manifest, args.current_manifest_hash
    if args.source_db is not None:
        if args.price_repair_receipt is None or args.price_repair_receipt_hash is None:
            parser.error("--source-db 需要 --price-repair-receipt 與 --price-repair-receipt-hash")
        from data_module.ml_restatement_current_capture import capture_restated_current_dataset

        current_manifest, current_hash = capture_restated_current_dataset(
            database_path=args.source_db, template_manifest_path=current_manifest,
            expected_template_manifest_hash=current_hash,
            price_repair_receipt=args.price_repair_receipt,
            expected_price_receipt_hash=args.price_repair_receipt_hash,
            symbols=args.symbols, output_root=args.output_root / "input_captures",
        )
    elif args.price_repair_receipt is not None or args.price_repair_receipt_hash is not None:
        parser.error("修訂 receipt 參數須與 --source-db 一起使用")
    result = run_bounded_restated_current_heads(
        fit_directory=args.fit_directory, expected_fit_receipt_hash=args.fit_receipt_hash,
        training_manifest=args.training_manifest,
        expected_training_manifest_hash=args.training_manifest_hash,
        current_manifest=current_manifest, expected_current_manifest_hash=current_hash,
        symbols=args.symbols, output_root=args.output_root,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
