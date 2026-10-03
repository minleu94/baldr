"""既有weekly之後的現況更新：單一writer、有界child、獨立終端證據。"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json,os,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root',required=True,type=Path)
    parser.add_argument('--db-path',required=True,type=Path)
    args=parser.parse_args(argv)
    root=args.output_root/'scheduled/current_fundamentals';root.mkdir(parents=True,exist_ok=True)
    status=root/'latest_status.json'
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    lock=(root/'writer.lock').open('a+b')
    acquired=False
    try:
        if os.name=='nt':
            import msvcrt
            lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
            try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);acquired=True
            except OSError:
                print('已有現況更新writer，拒絕重複執行');return 2
        command=[sys.executable,str(ROOT/'scripts/update_current_mops_statements.py'),'--output-root',str(args.output_root),'--db-path',str(args.db_path),'--parent-weekly-root',str(args.output_root),'--include-monthly','--status-path',str(status),'--apply','--confirm','append-current-mops-statements']
        log=root/(stamp+'.log')
        with log.open('wb') as stream:
            try:
                result=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=600,check=False)
                exit_code=result.returncode;outcome='completed' if exit_code==0 else 'failed'
            except subprocess.TimeoutExpired:
                exit_code=124;outcome='timeout_outcome_requires_readback'
        terminal={'schema_version':'scheduled-current-fundamentals-terminal.v1','completed_at':datetime.now(timezone.utc).isoformat(),'exit_code':exit_code,'status':outcome,'log_path':str(log),'child_status_path':str(status),'formal_pit_eligible':False,'natural_trigger_verified':False}
        (root/(stamp+'.terminal.json')).write_text(json.dumps(terminal,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(terminal,ensure_ascii=True))
        return exit_code
    finally:
        if acquired:
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
        lock.close()


if __name__=='__main__':raise SystemExit(main())
