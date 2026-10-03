"""法人候選觀測的版本化修訂投影；舊列與失敗checkpoint不可變。"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any

FIELDS = tuple(f'{group}_{suffix}' for group in ('foreign_investor', 'investment_trust', 'dealer') for suffix in ('buy', 'sell', 'net'))
TABLE = 'institutional_current_revisions'
SCHEMA = f'''CREATE TABLE IF NOT EXISTS {TABLE} (
 stock_code TEXT NOT NULL, decision_date TEXT NOT NULL, observation_hash TEXT NOT NULL,
 observed_at TEXT NOT NULL, source_version TEXT NOT NULL, payload_json TEXT NOT NULL,
 PRIMARY KEY(stock_code, decision_date, observation_hash));'''


def project_observation(conn: sqlite3.Connection, observation: dict[str, Any]) -> dict[str, Any]:
    """逐列驗證保留觀測，只追加與舊版不同／缺少的完整數值版本。"""
    payload_text = observation['canonical_payload_json']
    digest = 'sha256:' + hashlib.sha256(payload_text.encode('utf8')).hexdigest()
    if digest != observation['observation_hash']:
        raise ValueError('canonical observation hash不符')
    payload = json.loads(payload_text)
    if payload.get('schema_version') != 'phase3c-canonical-observation.v1':
        raise ValueError('canonical observation schema不符')
    observed = datetime.fromisoformat(observation['observed_at'].replace('Z','+00:00'))
    if observed.tzinfo is None or observed > datetime.now(timezone.utc) or payload.get('observation_at') != observation['observed_at']:
        raise ValueError('observation clock不符／未來時間')
    day = observation['decision_date']
    if date.fromisoformat(day) > observed.date():
        raise ValueError('資料日期晚於觀測時間')
    old = {r['stock_code']:dict(r) for r in conn.execute('SELECT * FROM institutional_flows WHERE decision_date=?',(day,))}
    records = payload.get('rows')
    if not isinstance(records,list) or len(records) != observation['row_count']:
        raise ValueError('canonical row_count不符')
    seen: set[str] = set()
    projected = []
    for row in records:
        code = row['stock_code']
        if code in seen or not code or row['decision_date'] != day or row['source_version'] not in {'twse-official-T86','tpex-official-3itrade'}:
            raise ValueError('canonical key或source identity不符')
        seen.add(code)
        if any(type(row.get(field)) is not int for field in FIELDS):
            raise ValueError('法人數值必須使用整數股數')
        if any(row[group+'_buy']-row[group+'_sell'] != row[group+'_net'] for group in ('foreign_investor','investment_trust','dealer')):
            raise ValueError('法人buy-sell與net不一致')
        previous = old.get(code)
        if previous is None or any(previous[field] != row[field] for field in FIELDS):
            projected.append((code,day,digest,observed.isoformat(),row['source_version'],json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':'))))
    conn.execute(SCHEMA)
    before=conn.total_changes
    for values in projected:
        existing=conn.execute(f'SELECT observed_at,source_version,payload_json FROM {TABLE} WHERE stock_code=? AND decision_date=? AND observation_hash=?',values[:3]).fetchone()
        if existing is not None and tuple(existing) != values[3:]:
            raise ValueError('修訂版本已存在且內容衝突')
    conn.executemany(f'INSERT OR IGNORE INTO {TABLE} VALUES (?,?,?,?,?,?)',projected)
    return {'decision_date':day,'observation_hash':digest,'observed_at':observed.isoformat(),'source_rows_verified':len(records),'revision_rows':len(projected),'inserted_count':conn.total_changes-before,'historical_pit_eligible':False,'original_rows_and_checkpoint_unchanged':True}


def read_current_institutional(conn: sqlite3.Connection, *, stock_code: str, observed_at: datetime, decision_date: date) -> dict[str, Any] | None:
    """在查詢clock之前合併候選舊版與修訂；資料日不等於可得日。"""
    if observed_at.tzinfo is None:
        raise ValueError('查詢clock必須含時區')
    base = conn.execute('SELECT * FROM institutional_flows WHERE stock_code=? AND decision_date<=? AND julianday(available_at)<=julianday(?) ORDER BY decision_date DESC LIMIT 1',(stock_code,decision_date.isoformat(),observed_at.isoformat())).fetchone()
    selected = dict(base) if base else None
    exists=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(TABLE,)).fetchone()
    if not exists:
        return selected
    revisions=conn.execute(f'SELECT * FROM {TABLE} WHERE stock_code=? AND decision_date<=? AND julianday(observed_at)<=julianday(?) ORDER BY decision_date DESC,julianday(observed_at) DESC LIMIT 2',(stock_code,decision_date.isoformat(),observed_at.isoformat())).fetchall()
    if not revisions:
        return selected
    revision=revisions[0]
    if len(revisions)>1 and revision['decision_date']==revisions[1]['decision_date'] and revision['observed_at']==revisions[1]['observed_at'] and revision['payload_json']!=revisions[1]['payload_json']:
        raise ValueError('同一觀測clock有不同修訂內容，不能任選版本')
    if selected is not None and revision['decision_date'] < selected['decision_date']:
        return selected
    observation=conn.execute("SELECT canonical_payload_json FROM phase3c_source_observations WHERE source='institutional' AND decision_date=? AND observation_hash=?",(revision['decision_date'],revision['observation_hash'])).fetchone()
    if observation is None or 'sha256:'+hashlib.sha256(observation[0].encode('utf8')).hexdigest()!=revision['observation_hash']:
        raise ValueError('修訂缺少有效canonical觀測綁定')
    row=json.loads(revision['payload_json'])
    matching=[r for r in json.loads(observation[0])['rows'] if r['stock_code']==stock_code]
    if matching!=[row]:
        raise ValueError('修訂值與canonical觀測不一致')
    row.update(available_at=revision['observed_at'],observed_at=revision['observed_at'],revision_observation_hash=revision['observation_hash'],quality='observed',historical_pit_eligible=False)
    return row
