"""明示runtime配置的UX20隔離daily owner；預設preflight，不註冊Task。"""
from __future__ import annotations
import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from app_module.rule_research_daily_owner import run_daily_owner
from app_module.rule_research_observation_acceptance import _QUALIFICATION
from app_module.rule_research_observation_acceptance import read_observation_days
from app_module.rule_research_daily_runtime_adapter import load_runtime_request, run_daily_runtime, offline_task_review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="明示隔離source/日期/policy/落點/配額；預設唯讀preflight，沒有生產預設。")
    parser.add_argument("--runtime-config")
    parser.add_argument("--target-date")
    parser.add_argument("--execute-isolated",action="store_true")
    parser.add_argument("--runtime-request", help="明示B12日曆／terminal／segment request，預設唯讀")
    parser.add_argument("--task-review", action="store_true", help="只輸出offline Task審查包，不註冊")
    parser.add_argument("--outcome-root", help="明示 UX21 隔離保存 root，唯讀列出同 parent 所有版本")
    args = parser.parse_args(argv)
    try:
        if args.runtime_request:
            if args.runtime_config or args.target_date or args.outcome_root or args.task_review and args.execute_isolated:
                raise ValueError("runtime_request_arguments_conflict")
            request = load_runtime_request(args.runtime_request)
            result = offline_task_review(request) if args.task_review else run_daily_runtime(request, execute=args.execute_isolated)
            print(json.dumps(result,ensure_ascii=False,sort_keys=True))
            return 0 if args.task_review or result["status"] in {"preflight_passed", "observed", "already_observed", "non_trading_day"} else 2
        if args.task_review:
            raise ValueError("task_review_requires_runtime_request")
        result = run_daily_owner(args.runtime_config,date.fromisoformat(args.target_date) if args.target_date else None,execute=args.execute_isolated)
        if args.outcome_root and result["status"] in {"observed", "already_observed"}:
            try:
                runtime = json.loads(Path(args.runtime_config).read_text(encoding="utf-8"))
                result["day_readiness"] = read_observation_days(runtime["policy_config"], runtime["acceptance_root"],
                    evaluated_at=datetime.now(timezone.utc), outcome_root=args.outcome_root)
                result["forward_day_readiness_status"] = "verified"
            except Exception as exc:
                result.update(forward_day_readiness_status="unavailable_or_unverified", forward_error=str(exc))
    except Exception as exc:
        result = {"status":"blocked","error_code":str(exc),"qualification":dict(_QUALIFICATION)}
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0 if result["status"] in {"preflight_passed","observed","already_observed"} and result.get("owner_status_capture_status") != "rejected_or_unverified" and result.get("forward_day_readiness_status") != "unavailable_or_unverified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
