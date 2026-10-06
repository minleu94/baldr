"""既有可信 H20 head 的個人啟用／回滾；預設預覽、不操作 Task。"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.recommendation.personal_h20_activation import (
    PersonalH20Activation, publish_personal_h20_activation, read_personal_h20_activation,
)
from scripts.qa_prepare_personal_h20_gross_contract import prepare_contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-root", required=True, type=Path)
    parser.add_argument("--personal-root", required=True, type=Path)
    parser.add_argument("--scope-id", required=True)
    parser.add_argument("--fit-receipt", type=Path)
    parser.add_argument("--fit-receipt-sha256")
    parser.add_argument("--history-start-date", default="2014-01-01")
    parser.add_argument("--expected-revision", required=True, type=int)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--enable", action="store_true")
    choice.add_argument("--disable", action="store_true")
    parser.add_argument("--execute", action="store_true", help="明示發佈配置 revision；不註冊／修改 Task")
    args = parser.parse_args(argv)
    if args.disable:
        current = read_personal_h20_activation(args.personal_root / "activation.json")
        if (current.scope_id, current.market_root) != (args.scope_id, str(args.market_root)):
            raise ValueError("activation_rollback_scope_mismatch")
        activation = replace(current, revision=args.expected_revision + 1, enabled=False)
        result = publish_personal_h20_activation(activation, expected_revision=args.expected_revision, execute=args.execute)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    if args.fit_receipt is None or args.fit_receipt_sha256 is None:
        parser.error("enable requires --fit-receipt and --fit-receipt-sha256")
    prepared = prepare_contract(args.fit_receipt, expected_fit_receipt_sha256=args.fit_receipt_sha256)
    contract = prepared["contract"]
    activation = PersonalH20Activation(
        revision=args.expected_revision + 1, enabled=args.enable, scope_id=args.scope_id,
        market_root=str(args.market_root), personal_root=str(args.personal_root),
        fit_receipt=str(args.fit_receipt), fit_receipt_sha256="sha256:" + args.fit_receipt_sha256.removeprefix("sha256:"),
        candidate_id=contract["candidate_id"], model_id=contract["model_id"],
        model_contract_hash=prepared["contract_hash"], history_start_date=args.history_start_date,
    )
    result = publish_personal_h20_activation(activation, expected_revision=args.expected_revision, execute=args.execute)
    result["holdout_evaluation"] = prepared["holdout_evaluation"]
    result["after_cost_evidence"] = "unproven"
    result["qualification"] = {"historical_pit_eligible": False, "formal_training_allowed": False,
                               "global_promotion": False, "trading_allowed": False}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
