"""用主機 Python 管理自有 frozen offscreen 測試程序與收據。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
exe=Path(os.environ.get('BALDR_PROBE_EXE', str(root/'dist/baldr/baldr.exe')))
case=Path(tempfile.mkdtemp(prefix='baldr portable 空間 '))
env={k:v for k,v in os.environ.items() if not k.startswith(('PERSONAL_','PIT_','CURRENT_RESTATED_','DAILY_MARKET_','RULE_RESEARCH_'))}
env.update(DATA_ROOT=str(case/'market'),OUTPUT_ROOT=str(case/'output'),LOCALAPPDATA=str(case/'local'),
    QT_QPA_PLATFORM='offscreen',PYTHONUTF8='1',PROFILE='prod',BALDR_CONFIG=str(case/'missing.json'),
    PYTHONDONTWRITEBYTECODE='1',MPLCONFIGDIR=str(case/'matplotlib'))
probe=root/'packaging'/sys.argv[1] if len(sys.argv)>1 else root/'packaging/portable_probe.py'
code='''import runpy,sys,traceback
sys._baldr_test_entry=sys.modules['__main__']
script=sys.argv.pop(1)
sys.argv[0]=script
try:
 runpy.run_path(script,run_name="__main__")
except Exception:
 traceback.print_exc()
 sys.exit(1)
'''
command=[str(exe),'-c',code,str(probe),str(case)]
try:
    child=subprocess.run(command,cwd=case,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    receipt={'exit':child.returncode,'stdout':child.stdout.decode('utf-8','replace'),'stderr':child.stderr.decode('utf-8','replace')}
except subprocess.TimeoutExpired as exc:
    receipt={'exit':124,'stdout':(exc.stdout or b'').decode('utf-8','replace'),'stderr':(exc.stderr or b'').decode('utf-8','replace'),'timeout':True}
receipt.update(case=str(case),exe=str(exe),probe=str(probe),native=False)
(case/'process.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
out=root/'output/packaging'
(out/(probe.stem+'_case.txt')).write_text(str(case),encoding='utf-8')
print(json.dumps(receipt,ensure_ascii=False))
raise SystemExit(receipt['exit'])
