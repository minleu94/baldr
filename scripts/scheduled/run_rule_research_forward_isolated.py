"""明示 UX21 來源的隔離研究入口；預設 preflight，沒有 Task 啟用。"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.rule_research_forward_store import run_forward_isolated
from app_module.rule_research_observation_acceptance import read_observation_days


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="UX21 隔離唯讀來源→研究成效；需明示設定，預設不保存")
    parser.add_argument("--runtime-config", required=True)
    parser.add_argument("--execute-isolated", action="store_true")
    parser.add_argument("--policy-config")
    parser.add_argument("--acceptance-root")
    args = parser.parse_args(argv)
    result = run_forward_isolated(args.runtime_config, execute=args.execute_isolated)
    if args.policy_config or args.acceptance_root:
        try:
            if not args.policy_config or not args.acceptance_root:
                raise ValueError("forward_daily_report_both_paths_required")
            config = json.loads(Path(args.runtime_config).read_text(encoding="utf-8"))
            result["day_readiness"] = read_observation_days(args.policy_config, args.acceptance_root,
                evaluated_at=datetime.now(timezone.utc), outcome_root=config["outcome_root"])
        except Exception as exc:
            result["daily_report_error"] = str(exc)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"preflight_passed", "saved"} and "daily_report_error" not in result else 2


if __name__ == "__main__":
    raise SystemExit(main())
