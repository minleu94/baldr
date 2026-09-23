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
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_restated_current_shadow(
        release_root=args.release_root,
        expected_release_identity_hash=args.release_identity_hash,
        dataset_manifest=args.dataset_manifest,
        expected_dataset_manifest_hash=args.dataset_manifest_hash,
        symbols=args.symbols,
        output_root=args.output_root,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
