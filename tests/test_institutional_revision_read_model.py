"""法人修訂不得破壞舊值、倒填時間或以任意hash選版本。"""
from datetime import date, datetime, timezone
import hashlib
import json
import sqlite3

import pytest

from data_module.institutional_revision_read_model import FIELDS, SCHEMA, TABLE, project_observation, read_current_institutional


def fixture():
    conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
    conn.execute('CREATE TABLE institutional_flows(stock_code TEXT,decision_date TEXT,available_at TEXT,'+','.join(f'{f} INTEGER' for f in FIELDS)+')')
    values=[v for _ in range(3) for v in (10,5,5)]
    conn.execute('INSERT INTO institutional_flows VALUES ('+','.join('?' for _ in range(12))+')',('2330','2026-09-17','2026-09-18T00:00:00Z',*values))
    row=dict(stock_code='2330',decision_date='2026-09-17',source_version='twse-official-T86',first_observed_at='2026-09-18T00:00:00Z',available_at='2026-09-18T00:00:00Z',**dict(zip(FIELDS,[v for _ in range(3) for v in (15,5,10)])))
    text=json.dumps({'schema_version':'phase3c-canonical-observation.v1','observation_at':'2026-10-02T11:26:00Z','rows':[row]},sort_keys=True,separators=(',',':'))
    obs={'canonical_payload_json':text,'observation_hash':'sha256:'+hashlib.sha256(text.encode()).hexdigest(),'observed_at':'2026-10-02T11:26:00Z','decision_date':'2026-09-17','row_count':1}
    conn.execute('CREATE TABLE phase3c_source_observations(source TEXT,decision_date TEXT,observation_hash TEXT,canonical_payload_json TEXT)')
    conn.execute('INSERT INTO phase3c_source_observations VALUES (?,?,?,?)',('institutional',obs['decision_date'],obs['observation_hash'],text))
    return conn,obs


def _register_observation(conn, *, observed_at, flow_values, source_version='twse-official-T86'):
    row=dict(
        stock_code='2330', decision_date='2026-09-17', source_version=source_version,
        first_observed_at='2026-09-18T00:00:00Z', available_at='2026-09-18T00:00:00Z',
        **dict(zip(FIELDS, flow_values)),
    )
    text=json.dumps({'schema_version':'phase3c-canonical-observation.v1','observation_at':observed_at,'rows':[row]},sort_keys=True,separators=(',',':'))
    obs={'canonical_payload_json':text,'observation_hash':'sha256:'+hashlib.sha256(text.encode()).hexdigest(),'observed_at':observed_at,'decision_date':'2026-09-17','row_count':1}
    conn.execute('INSERT INTO phase3c_source_observations VALUES (?,?,?,?)',('institutional',obs['decision_date'],obs['observation_hash'],text))
    return obs


def _revision_candidate(*, observed_at, flow_values, retry_marker, source_version='twse-official-T86'):
    row=dict(
        stock_code='2330', decision_date='2026-09-17', source_version=source_version,
        first_observed_at='2026-09-18T00:00:00Z', available_at='2026-09-18T00:00:00Z',
        **dict(zip(FIELDS, flow_values)), retry_marker=retry_marker,
    )
    text=json.dumps({'schema_version':'phase3c-canonical-observation.v1','observation_at':observed_at,'rows':[row]},sort_keys=True,separators=(',',':'))
    digest='sha256:'+hashlib.sha256(text.encode()).hexdigest()
    return row,text,digest


def _insert_revision_group(conn, records):
    conn.execute(SCHEMA)
    for row,text,digest in records:
        conn.execute('INSERT INTO phase3c_source_observations VALUES (?,?,?,?)',('institutional',row['decision_date'],digest,text))
        conn.execute(
            f'INSERT INTO {TABLE} VALUES (?,?,?,?,?,?)',
            (row['stock_code'],row['decision_date'],digest,json.loads(text)['observation_at'],row['source_version'],json.dumps(row,sort_keys=True,separators=(',',':'))),
        )


def _three_revision_clock_group(conn, *, conflicting: bool):
    observed_at='2026-10-03T00:00:00Z'
    same_values=[v for _ in range(3) for v in (10,5,5)]
    different_values=[v for _ in range(3) for v in (20,5,15)]
    if conflicting:
        for attempt in range(10000):
            same_a=_revision_candidate(observed_at=observed_at,flow_values=same_values,retry_marker=f'same-a-{attempt}')
            same_b=_revision_candidate(observed_at=observed_at,flow_values=same_values,retry_marker=f'same-b-{attempt}')
            different=_revision_candidate(observed_at=observed_at,flow_values=different_values,retry_marker=f'different-{attempt}')
            if different[2] < min(same_a[2],same_b[2]):
                records=[same_a,same_b,different]
                break
        else:
            raise AssertionError('could not make the three-row conflict fixture')
    else:
        records=[
            _revision_candidate(observed_at=observed_at,flow_values=same_values,retry_marker=f'same-{index}')
            for index in range(3)
        ]
    _insert_revision_group(conn,records)
    return records


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
    with pytest.raises(ValueError,match='row identity mismatch'):
        read_current_institutional(conn,stock_code='2330',observed_at=datetime(2026,10,3,tzinfo=timezone.utc),decision_date=date(2026,9,17))



def test_revision_can_revert_to_base_values_after_intermediate_revision():
    conn, first = fixture()
    project_observation(conn, first)
    base_values = [value for _ in range(3) for value in (10, 5, 5)]
    reversal = _register_observation(
        conn,
        observed_at='2026-10-03T11:26:00Z',
        flow_values=base_values,
        source_version='tpex-official-3itrade',
    )

    result = project_observation(conn, reversal)
    current = read_current_institutional(
        conn,
        stock_code='2330',
        observed_at=datetime(2026, 10, 4, tzinfo=timezone.utc),
        decision_date=date(2026, 9, 17),
    )

    assert result['inserted_count'] == 1
    assert current['foreign_investor_net'] == 5
    assert current['revision_observation_hash'] == reversal['observation_hash']
    assert current['historical_pit_eligible'] is False
    assert conn.execute('SELECT COUNT(*) FROM institutional_current_revisions').fetchone()[0] == 2


def test_source_version_only_change_does_not_create_revision():
    conn, _ = fixture()
    base_values = [value for _ in range(3) for value in (10, 5, 5)]
    observation = _register_observation(
        conn,
        observed_at='2026-10-03T11:26:00Z',
        flow_values=base_values,
        source_version='tpex-official-3itrade',
    )

    result = project_observation(conn, observation)

    assert result['revision_rows'] == 0
    assert result['inserted_count'] == 0
    assert conn.execute('SELECT COUNT(*) FROM institutional_current_revisions').fetchone()[0] == 0


def test_missing_or_future_observation_row_clock_is_rejected():
    conn, observation = fixture()
    payload = json.loads(observation['canonical_payload_json'])
    payload['rows'][0]['available_at'] = '2026-10-03T00:00:00Z'
    observation['canonical_payload_json'] = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    observation['observation_hash'] = 'sha256:' + hashlib.sha256(observation['canonical_payload_json'].encode()).hexdigest()
    conn.execute(
        'UPDATE phase3c_source_observations SET observation_hash=?, canonical_payload_json=?',
        (observation['observation_hash'], observation['canonical_payload_json']),
    )

    with pytest.raises(ValueError, match='available_at'):
        project_observation(conn, observation)


def test_three_same_clock_revisions_with_identical_flows_are_accepted():
    conn,_=fixture()
    _three_revision_clock_group(conn,conflicting=False)

    current=read_current_institutional(
        conn,
        stock_code='2330',
        observed_at=datetime(2026,10,4,tzinfo=timezone.utc),
        decision_date=date(2026,9,17),
    )

    assert current is not None
    assert [current[field] for field in FIELDS] == [v for _ in range(3) for v in (10,5,5)]


def test_three_same_clock_revisions_reject_any_conflict_in_reader_and_projector():
    conn,_=fixture()
    records=_three_revision_clock_group(conn,conflicting=True)
    assert records[2][2] < records[0][2] and records[2][2] < records[1][2]

    with pytest.raises(ValueError,match='conflicting institutional revisions share one observation clock'):
        read_current_institutional(
            conn,
            stock_code='2330',
            observed_at=datetime(2026,10,4,tzinfo=timezone.utc),
            decision_date=date(2026,9,17),
        )

    next_observation=_register_observation(
        conn,
        observed_at='2026-10-04T00:00:00Z',
        flow_values=[v for _ in range(3) for v in (20,5,15)],
    )
    with pytest.raises(ValueError,match='conflicting institutional revisions share one observation clock'):
        project_observation(conn,next_observation)

    assert conn.execute(f'SELECT COUNT(*) FROM {TABLE}').fetchone()[0] == 3
