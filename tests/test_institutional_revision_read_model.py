"""法人修訂不得破壞舊值、倒填時間或以任意hash選版本。"""
from datetime import date, datetime, timezone
import hashlib
import json
import sqlite3

import pytest

from data_module.institutional_revision_read_model import FIELDS, project_observation, read_current_institutional


def fixture():
    conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
    conn.execute('CREATE TABLE institutional_flows(stock_code TEXT,decision_date TEXT,available_at TEXT,'+','.join(f'{f} INTEGER' for f in FIELDS)+')')
    values=[v for _ in range(3) for v in (10,5,5)]
    conn.execute('INSERT INTO institutional_flows VALUES ('+','.join('?' for _ in range(12))+')',('2330','2026-09-17','2026-09-18T00:00:00Z',*values))
    row=dict(stock_code='2330',decision_date='2026-09-17',source_version='twse-official-T86',**dict(zip(FIELDS,[v for _ in range(3) for v in (15,5,10)])))
    text=json.dumps({'schema_version':'phase3c-canonical-observation.v1','observation_at':'2026-10-02T11:26:00Z','rows':[row]},sort_keys=True,separators=(',',':'))
    obs={'canonical_payload_json':text,'observation_hash':'sha256:'+hashlib.sha256(text.encode()).hexdigest(),'observed_at':'2026-10-02T11:26:00Z','decision_date':'2026-09-17','row_count':1}
    conn.execute('CREATE TABLE phase3c_source_observations(source TEXT,decision_date TEXT,observation_hash TEXT,canonical_payload_json TEXT)')
    conn.execute('INSERT INTO phase3c_source_observations VALUES (?,?,?,?)',('institutional',obs['decision_date'],obs['observation_hash'],text))
    return conn,obs


def test_revision_keeps_old_row_and_query_clock():
    conn,obs=fixture();old=[tuple(r) for r in conn.execute('SELECT * FROM institutional_flows')]
    result=project_observation(conn,obs)
    assert result['inserted_count']==1
    assert [tuple(r) for r in conn.execute('SELECT * FROM institutional_flows')]==old
    early=read_current_institutional(conn,stock_code='2330',observed_at=datetime(2026,9,20,tzinfo=timezone.utc),decision_date=date(2026,9,17))
    assert early['foreign_investor_net']==5
    current=read_current_institutional(conn,stock_code='2330',observed_at=datetime(2026,10,3,tzinfo=timezone.utc),decision_date=date(2026,9,17))
    assert current['foreign_investor_net']==10
    assert current['historical_pit_eligible'] is False
    assert project_observation(conn,obs)['inserted_count']==0


def test_tampered_canonical_observation_rejected():
    conn,obs=fixture();obs['canonical_payload_json']+=' '
    with pytest.raises(ValueError,match='hash'):
        project_observation(conn,obs)


def test_malformed_integer_quantity_rejected():
    conn,obs=fixture();payload=json.loads(obs['canonical_payload_json']);payload['rows'][0][FIELDS[0]]=15.5
    obs['canonical_payload_json']=json.dumps(payload)
    obs['observation_hash']='sha256:'+hashlib.sha256(obs['canonical_payload_json'].encode()).hexdigest()
    with pytest.raises(ValueError,match='整數'):
        project_observation(conn,obs)


def test_changed_revision_payload_is_not_consumed():
    conn,obs=fixture();project_observation(conn,obs)
    conn.execute("UPDATE institutional_current_revisions SET payload_json='{}'")
    with pytest.raises(ValueError,match='canonical觀測不一致'):
        read_current_institutional(conn,stock_code='2330',observed_at=datetime(2026,10,3,tzinfo=timezone.utc),decision_date=date(2026,9,17))
