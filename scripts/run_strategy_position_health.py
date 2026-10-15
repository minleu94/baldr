"""明選策略 checkpoint，沿原 evaluator 另存 v2 Health，供正常配置研究讀取。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.paper_checkpoint_ui_composition import PaperCheckpointAccountInputs
from app_module.personal_store_selection import resolve_personal_store_selection
from app_module.portfolio_research_account_reader import (
    StrategyPaperPortfolioResearchAccountReader, StrategyPaperResearchCheckpointSelection,
)
from app_module.position_health_strategy_archive import (
    prepare_strategy_health_baseline, publish_strategy_saved_health_receipt,
)
from app_module.position_health_transition_evaluator import evaluate_baseline_file
from app_module.strategy_paper_account_service import StrategyPaperAccountService
from data_module.config import TWStockConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="從明選策略帳建立同來源 Health 評估；不寫帳本或下單。")
    for name in StrategyPaperResearchCheckpointSelection.__dataclass_fields__:
        parser.add_argument("--" + name.replace("_", "-"), required=True)
    parser.add_argument("--output-dir", help="衍生評估封存根；預設 OUTPUT_ROOT/position_health_transition")
    for name in ("thesis-registry", "forward-binding", "condition-source", "metrics-source", "policy-source",
                 "calendar-cache", "temporary-closure-cache", "calendar-db", "calendar-start-date"):
        parser.add_argument("--" + name)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = TWStockConfig()
    inputs, error = PaperCheckpointAccountInputs.from_selection(
        resolve_personal_store_selection(config), contract_artifacts_root=config.paper_contract_artifacts_root,
        disabled_reason=config.paper_contract_artifacts_root_error,
    )
    if inputs is None:
        raise ValueError(error or "strategy_health_personal_inputs_unavailable")
    versions = config.resolve_output_path("backtest/versions")
    if not versions.is_dir():
        raise ValueError("strategy_health_saved_strategy_versions_missing")
    service = StrategyPaperAccountService(personal_paths=inputs.personal_paths,
        strategy_versions_root=versions, contract_artifacts_root=inputs.contract_artifacts_root)
    selection = StrategyPaperResearchCheckpointSelection(**{
        key: getattr(args, key) for key in StrategyPaperResearchCheckpointSelection.__dataclass_fields__})
    account_reader = StrategyPaperPortfolioResearchAccountReader(service, selection,
        decision_cutoff=datetime.now(timezone.utc))
    output = Path(args.output_dir).expanduser() if args.output_dir else config.output_root / "position_health_transition"
    if not output.is_absolute():
        raise ValueError("strategy_health_output_must_be_absolute")
    baseline = prepare_strategy_health_baseline(account_reader=account_reader,
        portfolio_id=selection.account_namespace, snapshot_id=selection.snapshot_id, output_dir=output)
    result = evaluate_baseline_file(baseline_path=baseline, output_dir=output,
        observed_at=datetime.now(timezone.utc), thesis_registry_path=args.thesis_registry,
        forward_binding_path=args.forward_binding, condition_source_path=args.condition_source,
        metrics_source_path=args.metrics_source, policy_source_path=args.policy_source,
        calendar_cache_path=args.calendar_cache, temporary_closure_path=args.temporary_closure_cache,
        calendar_db_path=args.calendar_db, calendar_start_date=args.calendar_start_date)
    reference = publish_strategy_saved_health_receipt(output_dir=output, result_path=result["result_path"],
        account_reader=account_reader, portfolio_id=selection.account_namespace, snapshot_id=selection.snapshot_id)
    print(json.dumps({"status": result["status"], "baseline_path": str(baseline),
        "result_path": result["result_path"], "receipt_id": reference.receipt_id,
        "receipt_sha256": reference.receipt_sha256, "blockers": result["blockers"],
        "warnings": result["warnings"], "research_only": True, "writes_account_ledger": False,
        "auto_action_allowed": False, "formal_credit": False}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
