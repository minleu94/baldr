"""把已保存的法人衝突觀測追加為現況修訂，保留舊列及原FAILED。"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from data_module.institutional_revision_read_model import project_observation
from data_module.p0_candidate_repository import validate_candidate_working_copy_path


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db-path',required=True,type=Path)
    parser.add_argument('--dates',required=True,nargs='+')
    parser.add_argument('--output-root',required=True,type=Path)
    parser.add_argument('--production-root',default='D:/Min/Python/Project/FA_Data',type=Path)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--confirm')
    args=parser.parse_args(argv)
    if args.apply and args.confirm!='append-current-institutional-revisions':
        parser.error('apply需要明確確認token')
    db=validate_candidate_working_copy_path(args.db_path,production_data_root=args.production_root,production_db_path=args.production_root/'sqlite/twstock.db')
    if not db.is_file(): raise FileNotFoundError(db)
    root=args.output_root/('institutional-revisions-'+uuid4().hex)
    root.mkdir(parents=True,exist_ok=False)
    backup=root/'before.sqlite'
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as source, sqlite3.connect(backup) as target:
        source.backup(target)
        if target.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise ValueError('備份quick_check失敗')
    # review僅在隔離備份內投影；apply完整交易只追加新表。
    with sqlite3.connect(db if args.apply else backup) as conn:
        conn.row_factory=sqlite3.Row
        conn.execute('BEGIN IMMEDIATE')
        results=[]
        for day in args.dates:
            observation=conn.execute("SELECT * FROM phase3c_source_observations WHERE source='institutional' AND decision_date=? ORDER BY julianday(observed_at) DESC LIMIT 1",(day,)).fetchone()
            if observation is None: raise ValueError('缺少來源觀測:'+day)
            results.append(project_observation(conn,dict(observation)))
        conn.commit()
    result={'schema_version':'institutional-current-revision-materialization.v1','status':'applied' if args.apply else 'reviewed_on_copy','observed_at':datetime.now(timezone.utc).isoformat(),'database':str(db),'backup_file':str(backup),'results':results,'original_checkpoint_rewritten':False,'historical_pit_eligible':False}
    (root/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(result,run_root=str(root)),ensure_ascii=True,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
