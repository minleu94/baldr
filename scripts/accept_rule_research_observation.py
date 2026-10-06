"""固定觀測日的隔離接受／唯讀報表入口；預設預覽，不部署排程。"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app_module.rule_research_observation_acceptance import preview_or_accept_observation, read_observation_days


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="明示日期／cutoff／parent pin；預設只預覽研究接受記錄，不開市場DB。")
    parser.add_argument("--policy-config", required=True)
    parser.add_argument("--acceptance-root", required=True, help="repo output/qa或Temp專用隔離子目錄，不與來源重疊")
    parser.add_argument("--evaluated-at", required=True, help="含時區ISO評估時刻，不能晚於現在；不以最新日替代")
    parser.add_argument("--parent-receipt", help="明示parents/<identity>/receipt.json；省略則只讀日覆蓋報表")
    parser.add_argument("--accept", action="store_true", help="明示保存接受或未完整記錄；沒有此flag不寫入")
    args = parser.parse_args(argv)
    try:
        evaluated = datetime.fromisoformat(args.evaluated_at)
        if args.accept and not args.parent_receipt:
            raise ValueError("accept requires explicit parent-receipt")
        if args.parent_receipt:
            result = preview_or_accept_observation(args.policy_config, args.parent_receipt, args.acceptance_root,
                accept=args.accept, evaluated_at=evaluated)
        else:
            result = read_observation_days(args.policy_config, args.acceptance_root, evaluated_at=evaluated)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        incomplete = result.get("candidate", {}).get("acceptance_status") == "recorded_incomplete_observation"
        return 2 if incomplete or result.get("day_readiness_status") == "rejected" else 0
    except Exception as exc:
        print(json.dumps({"status": "rejected", "error_code": str(exc), "research_only": True,
                          "acceptance_saved": "unknown" if args.accept else False,
                          "evidence_action": "保留既有parent及接受目錄，核對收據後重試；拒絕不等於沒有保存殘件"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
