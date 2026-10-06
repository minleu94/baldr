"""明示runtime配置的UX20隔離daily owner；預設preflight，不註冊Task。"""
from __future__ import annotations
import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from app_module.rule_research_daily_owner import run_daily_owner
from app_module.rule_research_observation_acceptance import _QUALIFICATION


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="明示隔離source/日期/policy/落點/配額；預設唯讀preflight，沒有生產預設。")
    parser.add_argument("--runtime-config")
    parser.add_argument("--target-date")
    parser.add_argument("--execute-isolated",action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_daily_owner(args.runtime_config,date.fromisoformat(args.target_date) if args.target_date else None,execute=args.execute_isolated)
    except Exception as exc:
        result = {"status":"blocked","error_code":str(exc),"qualification":dict(_QUALIFICATION)}
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0 if result["status"] in {"preflight_passed","observed","already_observed"} and result.get("owner_status_capture_status") != "rejected_or_unverified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
