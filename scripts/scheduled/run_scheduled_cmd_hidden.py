"""以無命令視窗的子程序執行固定四個既有 Task，保存獨立啟動／結束證據。

Windows Task 以 pythonw.exe 呼叫本檔；原 CMD、觸發時間、權限與 child
行為保留。這份收據只證明程序退出，不授予資料、模型或整鏈成功資格。
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
TASK_SCRIPTS = {
    "baldr-ml-direct-chain-maintainer": "run_ml_direct_chain_maintenance.cmd",
    "baldr-paper-portfolio-daily": "run_paper_portfolio_daily.cmd",
    "baldr-pit-sector-membership-preopen-capture-daily": "run_pit_sector_membership_preopen_capture.cmd",
    "baldr-ml-allocation-forward-daily": "run_ml_allocation_forward_daily.cmd",
}


def run_task(task: str) -> int:
    script = ROOT / "scripts" / "scheduled" / TASK_SCRIPTS[task]
    if not script.is_file() or script.is_symlink():
        raise ValueError("固定 Task CMD 不存在或不是一般檔案")
    now = datetime.now(timezone.utc)
    run_root = ROOT / "output" / "scheduled_launches" / task / (now.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8])
    run_root.mkdir(parents=True, exist_ok=False)
    receipt = {
        "schema_version": "scheduled-hidden-launch.v1", "task": task,
        "script_path": str(script), "started_at": now.isoformat(),
        "launcher_pid": os.getpid(), "child_pid": None,
        "status": "running", "exit_code": None,
        "pipeline_success_claimed": False,
    }
    with (run_root / "started.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
    returncode = 2
    try:
        command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(script)]
        with (run_root / "stdout.bin").open("xb") as stdout, (run_root / "stderr.bin").open("xb") as stderr:
            with subprocess.Popen(
                command, cwd=ROOT, stdout=stdout, stderr=stderr,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ) as child:
                receipt["child_pid"] = child.pid
                try:
                    returncode = child.wait()
                except BaseException:
                    child.kill()
                    child.wait()
                    raise
        receipt["status"] = "exited"
    except BaseException as error:
        receipt.update(status="launcher_failed", error_type=type(error).__name__, error=str(error)[:500])
    finally:
        receipt.update(exit_code=returncode, completed_at=datetime.now(timezone.utc).isoformat())
        with (run_root / "terminal.json").open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
    return returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, choices=tuple(TASK_SCRIPTS))
    return run_task(parser.parse_args().task)


if __name__ == "__main__":
    raise SystemExit(main())
