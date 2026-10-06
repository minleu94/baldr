"""隔離 CLI／scheduler preflight；不註冊或觸發 Task。"""
from pathlib import Path
import json
import os
import subprocess
import sys
case = Path(sys.argv[1])
commands = [
    ['--version'],
    ['scripts/scheduled/run_daily_data_update_quick.py', '--help'],
    ['-m', 'scripts.scheduled.run_daily_data_update_quick', '--help'],
    ['scripts/scheduled/run_rule_research_daily_isolated.py'],
    ['-c', 'print("UTF8 中文測試")'],
    ['-c', 'raise RuntimeError("fixture failure")'],
]
results = []
for args in commands:
    child = subprocess.run([sys.executable, *args], cwd=case, env=os.environ.copy(),
                           capture_output=True, encoding='utf-8', timeout=30)
    expected = (2 if args == ['scripts/scheduled/run_rule_research_daily_isolated.py']
                else 1 if 'fixture failure' in args[-1] else 0)
    assert child.returncode == expected, (args, child.returncode, child.stderr)
    results.append(dict(args=args, exit=child.returncode, stdout=child.stdout, stderr=child.stderr))
assert 'unconfigured' in results[3]['stdout'], results[3]
assert 'UTF8 中文測試' in results[4]['stdout'], results[4]
(case / 'portable_cli_probe.json').write_text(json.dumps(dict(status='passed', results=results,
    native=False, task_registered=False, task_triggered=False), ensure_ascii=False, indent=2), encoding='utf-8')
