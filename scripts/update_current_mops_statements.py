"""受控取得兩市場MOPS現況財報，保存原件後正規化並追加非PIT觀測。"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib,json,sqlite3,sys,os
from pathlib import Path
from uuid import uuid4
import requests

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from data_module.mops_current_statement_html import STATEMENTS,parse_current_statement_html
from data_module.current_fundamental_snapshots import insert_observations
from data_module.scheduled_research_acquisition_binding import read_bound_json, _read_stable_bytes
from data_module.scheduled_research_acquisition_binding import verify_weekly_acquisition


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--period')
    parser.add_argument('--output-root',required=True,type=Path)
    parser.add_argument('--db-path',type=Path)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--confirm')
    parser.add_argument('--captured-run',type=Path)
    parser.add_argument('--include-monthly',action='store_true')
    parser.add_argument('--parent-weekly-root',type=Path)
    parser.add_argument('--status-path',type=Path)
    parser.add_argument('--monthly-snapshot',type=Path)
    args=parser.parse_args(argv)
    if args.apply and (args.confirm!='append-current-mops-statements' or args.db_path is None): parser.error('apply需要DB及明確確認token')
    from scripts.scheduled.data_freshness_probe import _expected_latest_statement_period, _expected_latest_monthly_period
    from zoneinfo import ZoneInfo
    today=datetime.now(ZoneInfo('Asia/Taipei')).date()
    if args.period is None: args.period=_expected_latest_statement_period(today)
    parent=None
    if args.parent_weekly_root is not None:
        parent=verify_weekly_acquisition(args.parent_weekly_root,now=datetime.now(timezone.utc),repository_root=ROOT)
        if parent.get('status')!='verified': raise ValueError('weekly父收據未驗證，不能啟動現況更新')
        parent_receipt=read_bound_json(Path(parent['receipt_path']),expected_sha256=parent['receipt_sha256'])
        if args.db_path is None or Path(parent_receipt.payload['source_db_path']).resolve()!=args.db_path.resolve():
            raise ValueError('現況更新DB與weekly父來源身分不符')
    year,quarter=map(int,args.period.split('-Q'))
    root=args.output_root/('current-mops-statements-'+uuid4().hex);root.mkdir(parents=True,exist_ok=False)
    records=[];receipts=[];failed=False
    def publish(payload:dict)->None:
        if args.status_path is not None:
            args.status_path.parent.mkdir(parents=True,exist_ok=True)
            temporary=args.status_path.with_name(args.status_path.name+'.'+uuid4().hex+'.tmp')
            temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf8')
            os.replace(temporary,args.status_path)
    publish({'schema_version':'current-mops-statements-status.v1','status':'running','started_at':datetime.now(timezone.utc).isoformat(),'run_root':str(root),'parent_weekly_binding':parent,'formal_pit_eligible':False})
    saved_capture=read_bound_json(args.captured_run/'receipt.json') if args.captured_run else None
    if saved_capture is not None and (saved_capture.payload.get('schema_version')!='current-mops-statements-update.v1' or saved_capture.payload.get('period')!=args.period):
        raise ValueError('既有capture身分／期別不符')
    for market in ['twse','tpex']:
        for statement,(route,_,_) in STATEMENTS.items():
            params={'encodeURIComponent':'1','step':'1','firstin':'1','off':'1','isQuery':'Y','TYPEK':'sii' if market=='twse' else 'otc','year':str(year-1911),'season':f'{quarter:02d}'}
            url=f'https://mopsov.twse.com.tw/mops/web/ajax_{route}'
            receipt={'requested_url':url,'params':params,'market':market,'statement':statement,'started_at':datetime.now(timezone.utc).isoformat()}
            try:
                if saved_capture is not None:
                    candidates=[r for r in saved_capture.payload['requests'] if r['market']==market and r['statement']==statement]
                    if len(candidates)!=1 or candidates[0].get('http_status')!=200 or candidates[0]['requested_url']!=url or candidates[0]['params']!=params:
                        raise ValueError('既有capture的HTTP／request身分不符')
                    original=candidates[0]
                    original_path=args.captured_run/f'{market}_{statement}.html'
                    body=_read_stable_bytes(original_path,max_bytes=32*1024*1024)
                    if len(body)!=original['bytes'] or hashlib.sha256(body).hexdigest()!=original['sha256']:
                        raise ValueError('既有raw hash不符')
                    raw_path=root/f'{market}_{statement}.html';raw_path.write_bytes(body)
                    receipt.update(http_status=200,final_url=original['final_url'],bytes=len(body),sha256=original['sha256'],raw_file=str(raw_path),original_capture_receipt_sha256=saved_capture.sha256,original_started_at=original['started_at'],http_request_performed=False)
                else:
                  with requests.post(url,data=params,timeout=(10,30),stream=True) as response:
                    chunks=[];size=0
                    for chunk in response.iter_content(65536):
                        size+=len(chunk)
                        if size>32*1024*1024: raise ValueError('官方回應超過有界上限')
                        chunks.append(chunk)
                    body=b''.join(chunks);raw_path=root/f'{market}_{statement}.html';raw_path.write_bytes(body)
                    receipt.update(http_status=response.status_code,final_url=response.url,bytes=size,sha256=hashlib.sha256(body).hexdigest(),raw_file=str(raw_path))
                    response.raise_for_status()
                observed=datetime.now(timezone.utc)
                rows,summary=parse_current_statement_html(body.decode('utf8'),market=market,period=args.period,statement=statement,observed_at=observed)
                records.extend(rows);receipt.update(status='normalized',completed_at=observed.isoformat(),normalization=summary)
            except Exception as exc:
                receipt.update(status='failed',error_type=type(exc).__name__,reason=str(exc));failed=True
            receipts.append(receipt);print(json.dumps(receipt,ensure_ascii=True),flush=True)
    monthly=None
    if args.include_monthly:
        try:
            from data_module.monthly_revenue_snapshot_harvester import build_mops_monthly_revenue_snapshot,write_mops_snapshot_csv
            from data_module.current_monthly_revenue_materialization import plan_current_revenue
            month=_expected_latest_monthly_period(today)
            if args.monthly_snapshot is not None:
                monthly_path=args.monthly_snapshot
            else:
                monthly_root=root/'monthly';monthly_path=monthly_root/'snapshot.csv'
                capture=build_mops_monthly_revenue_snapshot(start_period=month,end_period=month,markets=('twse','tpex'),fetch_date=today,save_html_dir=monthly_root/'raw_html')
                if capture.diagnostics or not capture.valid_candidate: raise ValueError('月營收抓取未完整')
                write_mops_snapshot_csv(monthly_path,capture.rows)
            plan=plan_current_revenue(monthly_path);records.extend(plan.records);monthly=plan.custody
            if monthly['periods']!=[month]: raise ValueError('月營收既有快照不是目前應檢查期別')
        except Exception as exc:
            failed=True;monthly={'status':'failed','reason':str(exc)}
    result={'schema_version':'current-mops-statements-update.v1','period':args.period,'requests':receipts,'monthly':monthly,'parent_weekly_binding':parent,'run_root':str(root),'normalized_rows':len(records),'stock_count':len({r['stock_code'] for r in records}),'status':'blocked' if failed else 'candidate_verified','historical_pit_eligible':False,'formal_statement_items_written':False,'issuer_denominator_complete':False}
    if args.apply and not failed:
        db=args.db_path
        if db is None or not db.is_file(): raise FileNotFoundError(db)
        backup=root/'before.sqlite'
        try:
            with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(backup) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise ValueError('備份quick_check失敗')
            with sqlite3.connect(db) as conn:
                conn.execute('BEGIN IMMEDIATE');inserted=insert_observations(conn,records);conn.commit()
            result.update(status='applied',inserted_count=inserted,backup_file=str(backup),database=str(db))
        except Exception as exc:
            failed=True
            result.update(status='apply_failed',error_type=type(exc).__name__,reason=str(exc),backup_file=str(backup))
    (root/'normalized_rows.json').write_text(json.dumps(records,ensure_ascii=False),encoding='utf8')
    result['normalized_artifact_sha256']=hashlib.sha256((root/'normalized_rows.json').read_bytes()).hexdigest()
    (root/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    publish({'schema_version':'current-mops-statements-status.v1','status':result['status'],'completed_at':datetime.now(timezone.utc).isoformat(),'run_root':str(root),'receipt_path':str(root/'receipt.json'),'receipt_sha256':hashlib.sha256((root/'receipt.json').read_bytes()).hexdigest(),'normalized_rows':len(records),'formal_pit_eligible':False})
    print(json.dumps(result,ensure_ascii=True,indent=2))
    return 2 if failed else 0


if __name__=='__main__':raise SystemExit(main())
