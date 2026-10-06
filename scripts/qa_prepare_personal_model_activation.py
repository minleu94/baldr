"""讀回原個人模型 inspector，保存啟用前收據；不載入模型或啟用 Task。"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--learning-output-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--receipt-path", type=Path, required=True)
    args = parser.parse_args(argv)
    for name in ("data_root", "learning_output_root", "candidate_root", "receipt_path"):
        if not getattr(args, name).is_absolute():
            parser.error(f"{name} 必須是明示絕對路徑")
    receipt = args.receipt_path.resolve()
    for source in (args.data_root, args.learning_output_root, args.candidate_root):
        source = source.resolve()
        if receipt == source or source in receipt.parents:
            parser.error("receipt 必須在資料與 learning 來源樹之外")
    if not receipt.parent.is_dir():
        parser.error("receipt parent 必須已存在")

    from app_module.recommendation.personal_candidate_inventory import (
        inspect_personal_calibration_candidate,
    )

    entry = inspect_personal_calibration_candidate(
        candidate_root=args.candidate_root,
        data_root=args.data_root,
        explicit_output_root=args.learning_output_root,
    )
    payload = {
        "schema_version": "personal-model-activation-preflight.v1",
        "operation": "original_readonly_inspector",
        "model_deserialized": False,
        "activation_performed": False,
        "task_modified": False,
        "candidate": asdict(entry),
        "interpretation": "metadata/來源讀回；不授 artifact 載入或提升統計資格",
    }
    # 新建收據，不覆蓋既有檔案；來源 inspector 保留原容量與 no-follow 契約。
    with receipt.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"status": entry.status, "reason": entry.reason_code,
                      "receipt": str(receipt)}, ensure_ascii=False))
    return 0 if entry.candidate is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
